/*
 * Copyright (c) 2021, Linus Groh <linusg@serenityos.org>
 * Copyright (c) 2021, Idan Horowitz <idan.horowitz@serenityos.org>
 *
 * SPDX-License-Identifier: MIT
 */

#include "$262Object.h"
#include "AgentObject.h"
#include "GlobalObject.h"
#include "IsHTMLDDA.h"
#include <LibJS/Heap/Cell.h>
#include <LibJS/Interpreter.h>
#include <LibJS/Lexer.h>
#include <LibJS/Parser.h>
#include <LibJS/Runtime/ArrayBuffer.h>
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
    m_is_htmldda = vm().heap().allocate<IsHTMLDDA>(global_object, global_object);

    u8 attr = JS::Attribute::Writable | JS::Attribute::Configurable;
    define_native_function("clearKeptObjects", clear_kept_objects, 0, attr);
    define_native_function("createRealm", create_realm, 0, attr);
    define_native_function("detachArrayBuffer", detach_array_buffer, 1, attr);
    define_native_function("evalScript", eval_script, 1, attr);

    define_direct_property("agent", m_agent, attr);
    define_direct_property("gc", global_object.get_without_side_effects("gc"), attr);
    define_direct_property("global", &global_object, attr);
    define_direct_property("IsHTMLDDA", m_is_htmldda, attr);
}

void $262Object::visit_edges(JS::Cell::Visitor& visitor)
{
    Base::visit_edges(visitor);
    visitor.visit(m_agent);
    visitor.visit(m_is_htmldda);
}

JS_DEFINE_NATIVE_FUNCTION($262Object::clear_kept_objects)
{
    vm.finish_execution_generation();
    return JS::js_undefined();
}

JS_DEFINE_NATIVE_FUNCTION($262Object::create_realm)
{
    auto realm = vm.heap().allocate_without_global_object<GlobalObject>();
    realm->initialize_global_object();
    return JS::Value(realm->$262());
}

// 25.1.2.3 DetachArrayBuffer, https://tc39.es/ecma262/#sec-detacharraybuffer
JS_DEFINE_NATIVE_FUNCTION($262Object::detach_array_buffer)
{
    auto array_buffer = vm.argument(0);
    if (!array_buffer.is_object() || !is<JS::ArrayBuffer>(array_buffer.as_object()))
        return vm.throw_completion<JS::TypeError>(global_object);
    auto& array_buffer_object = static_cast<JS::ArrayBuffer&>(array_buffer.as_object());
    if (!JS::same_value(array_buffer_object.detach_key(), vm.argument(1)))
        return vm.throw_completion<JS::TypeError>(global_object);
    array_buffer_object.detach_buffer();
    return JS::js_null();
}

JS_DEFINE_NATIVE_FUNCTION($262Object::eval_script)
{
    auto source = TRY(vm.argument(0).to_string(global_object));
    auto parser = JS::Parser(JS::Lexer(source));
    auto program = parser.parse_program();
    if (parser.has_errors())
        return vm.throw_completion<JS::SyntaxError>(global_object, parser.errors()[0].to_string());
    vm.interpreter().run(global_object, *program);
    if (auto* exception = vm.exception())
        return JS::throw_completion(exception->value());
    return JS::js_undefined();
}
