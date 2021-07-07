/*
 * Copyright (c) 2021, Linus Groh <linusg@serenityos.org>
 *
 * SPDX-License-Identifier: MIT
 */

#include "GlobalObject.h"
#include <AK/Format.h>
#include <AK/JsonObject.h>
#include <AK/Result.h>
#include <AK/String.h>
#include <AK/Vector.h>
#include <LibCore/ArgsParser.h>
#include <LibCore/File.h>
#include <LibJS/Bytecode/BasicBlock.h>
#include <LibJS/Bytecode/Generator.h>
#include <LibJS/Bytecode/Interpreter.h>
#include <LibJS/Bytecode/PassManager.h>
#include <LibJS/Interpreter.h>
#include <LibJS/Lexer.h>
#include <LibJS/Parser.h>
#include <LibJS/Runtime/VM.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>

static Result<ByteBuffer, JsonObject> read_file(String const& path)
{
    if (path.is_null()) {
        auto file = Core::File::standard_input();
        return file->read_all();
    } else {
        auto file = Core::File::construct(path);
        if (!file->open(Core::OpenMode::ReadOnly)) {
            JsonObject error_object;
            error_object.set("details", String::formatted("Failed to open '{}': {}", path, file->error_string()));
            return error_object;
        }
        return file->read_all();
    }
}

static Result<NonnullRefPtr<JS::Program>, JsonObject> parse_program(StringView source)
{
    auto parser = JS::Parser(JS::Lexer(source));
    auto program = parser.parse_program();
    if (parser.has_errors()) {
        JsonObject error_object;
        error_object.set("phase", "parse");
        error_object.set("type", "SyntaxError");
        error_object.set("details", parser.errors()[0].to_string());
        return error_object;
    }
    return program;
}

template<typename InterpreterT>
static Result<void, JsonObject> run_program(InterpreterT& interpreter, JS::Program const& program)
{
    auto& vm = interpreter.vm();
    if constexpr (IsSame<InterpreterT, JS::Interpreter>) {
        interpreter.run(interpreter.global_object(), program);
    } else {
        auto unit = JS::Bytecode::Generator::generate(program);
        auto& passes = JS::Bytecode::Interpreter::optimization_pipeline();
        passes.perform(unit);
        interpreter.run(unit);
    }
    if (auto* exception = vm.exception()) {
        vm.clear_exception();
        JsonObject error_object;
        error_object.set("phase", "runtime");
        if (exception->value().is_object()) {
            auto& object = exception->value().as_object();

            auto name = object.get_without_side_effects("name");
            if (!name.is_empty() && !name.is_accessor()) {
                error_object.set("type", name.to_string_without_side_effects());
            } else {
                auto constructor = object.get_without_side_effects("constructor");
                if (constructor.is_object()) {
                    // NOTE: Would be nice to use get_without_side_effects() here, but for
                    // whatever reason OrdinaryFunctionObject's .name and .length are currently
                    // native properties, so that's not going to work.
                    name = constructor.as_object().get("name");
                    if (!name.is_empty())
                        error_object.set("type", name.to_string_without_side_effects());
                }
            }

            auto message = object.get_without_side_effects("message");
            if (!message.is_empty() && !message.is_accessor())
                error_object.set("details", message.to_string_without_side_effects());
        }
        if (!error_object.has("type"))
            error_object.set("type", exception->value().to_string_without_side_effects());
        return error_object;
    }
    return {};
}

template<typename InterpreterT>
static Result<void, JsonObject> run_script(String const& path, InterpreterT& interpreter)
{
    auto source_or_error = read_file(path);
    if (source_or_error.is_error())
        return source_or_error.release_error();
    auto source = source_or_error.release_value();

    auto program_or_error = parse_program(source);
    if (program_or_error.is_error())
        return program_or_error.release_error();
    auto program = program_or_error.release_value();

    return run_program(interpreter, *program);
}

int main(int argc, char** argv)
{
    Vector<String> harness_files;
    bool use_bytecode = false;

    Core::ArgsParser args_parser;
    args_parser.set_general_help("LibJS test262 runner for individual tests");
    args_parser.add_option(use_bytecode, "Use the bytecode interpreter", "use-bytecode", 'b');
    args_parser.add_positional_argument(harness_files, "Harness files to execute prior to test execution", "paths", Core::ArgsParser::Required::No);
    args_parser.parse(argc, argv);

    // All the piping stuff is based on https://stackoverflow.com/a/956269.

    constexpr auto BUFFER_SIZE = 1 * KiB;
    char buffer[BUFFER_SIZE] = {};

    auto saved_stdout = dup(STDOUT_FILENO);
    if (saved_stdout < 0) {
        perror("dup");
        return 1;
    }

    int stdout_pipe[2];
    if (pipe(stdout_pipe) < 0) {
        perror("pipe");
        return 1;
    }

    auto flags = fcntl(stdout_pipe[0], F_GETFL);
    flags |= O_NONBLOCK;
    fcntl(stdout_pipe[0], F_SETFL, flags);

    if (dup2(stdout_pipe[1], STDOUT_FILENO) < 0) {
        perror("dup2");
        return 1;
    }
    if (close(stdout_pipe[1]) < 0) {
        perror("close");
        return 1;
    }

    auto vm = JS::VM::create();
    auto ast_interpreter = JS::Interpreter::create<GlobalObject>(*vm);
    OwnPtr<JS::Bytecode::Interpreter> bytecode_interpreter = nullptr;
    if (use_bytecode)
        bytecode_interpreter = make<JS::Bytecode::Interpreter>(ast_interpreter->global_object());

    auto run_it = [&](String const& path) {
        if (use_bytecode)
            return run_script(path, *bytecode_interpreter);
        return run_script(path, *ast_interpreter);
    };

    JsonObject result_object;

    for (auto& path : harness_files) {
        auto result = run_it(path);
        if (result.is_error()) {
            result_object.set("harness_error", true);
            result_object.set("harness_file", path);
            result_object.set("error", result.release_error());
            break;
        }
    }
    if (!result_object.has("harness_error")) {
        auto result = run_it({});
        if (result.is_error())
            result_object.set("error", result.release_error());
    }

    fflush(stdout);
    auto nread = read(stdout_pipe[0], buffer, BUFFER_SIZE);
    if (dup2(saved_stdout, STDOUT_FILENO) < 0) {
        perror("dup2");
        return 1;
    }
    if (close(stdout_pipe[0]) < 0) {
        perror("close");
        return 1;
    }

    if (nread > 0)
        result_object.set("output", String { buffer, static_cast<size_t>(nread) });

    outln("{}", result_object.to_string());
    return 0;
}
