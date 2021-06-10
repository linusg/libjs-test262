/*
 * Copyright (c) 2021, Linus Groh <linusg@serenityos.org>
 *
 * SPDX-License-Identifier: MIT
 */

#include "$262Object.h"
#include "AgentObject.h"
#include "GlobalObject.h"
#include <LibJS/Heap/Cell.h>
#include <LibJS/Interpreter.h>
#include <LibJS/Lexer.h>
#include <LibJS/Parser.h>
#include <LibJS/Runtime/GlobalObject.h>
#include <LibJS/Runtime/Object.h>

$262Object::$262Object(JS::GlobalObject& global_object)
    : JS::Object(JS::Object::ConstructWithoutPrototypeTag::Tag, global_object)
{
}

void $262Object::initialize(JS::GlobalObject& global_object)
{
    Base::initialize(global_object);

    m_agent = vm().heap().allocate<AgentObject>(global_object, global_object);

    define_native_function("createRealm", create_realm, 0);
    define_native_function("evalScript", eval_script, 1);

    define_property("agent", m_agent);
    define_property("gc", global_object.get("gc"));
    define_property("global", &global_object);
    // TODO: detachArrayBuffer
}

void $262Object::visit_edges(JS::Cell::Visitor& visitor)
{
    Base::visit_edges(visitor);
    visitor.visit(m_agent);
}

JS_DEFINE_NATIVE_FUNCTION($262Object::create_realm)
{
    auto realm = vm.heap().allocate_without_global_object<GlobalObject>();
    realm->initialize_global_object();
    return JS::Value(realm->$262());
}

JS_DEFINE_NATIVE_FUNCTION($262Object::eval_script)
{
    auto source = vm.argument(0).to_string(global_object);
    if (vm.exception())
        return {};
    auto parser = JS::Parser(JS::Lexer(source));
    auto program = parser.parse_program();
    if (parser.has_errors()) {
        vm.throw_exception<JS::SyntaxError>(global_object, parser.errors()[0].to_string());
        return {};
    }
    vm.interpreter().run(global_object, *program);
    if (vm.exception())
        return {};
    return JS::js_undefined();
}
