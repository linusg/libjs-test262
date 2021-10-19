/*
 * Copyright (c) 2021, Linus Groh <linusg@serenityos.org>
 *
 * SPDX-License-Identifier: MIT
 */

#include "AgentObject.h"
#include <LibJS/Runtime/GlobalObject.h>
#include <LibJS/Runtime/Object.h>
#include <chrono>
#include <unistd.h>

AgentObject::AgentObject(JS::GlobalObject& global_object)
    : JS::Object(JS::Object::ConstructWithoutPrototypeTag::Tag, global_object)
{
}

void AgentObject::initialize(JS::GlobalObject& global_object)
{
    Base::initialize(global_object);

    u8 attr = JS::Attribute::Writable | JS::Attribute::Configurable;
    define_native_function("monotonicNow", monotonic_now, 0, attr);
    define_native_function("sleep", sleep, 1, attr);
    // TODO: broadcast
    // TODO: getReport
    // TODO: start
}

JS_DEFINE_NATIVE_FUNCTION(AgentObject::monotonic_now)
{
    auto time_since_epoch = std::chrono::system_clock::now().time_since_epoch();
    auto milliseconds = std::chrono::duration_cast<std::chrono::milliseconds>(time_since_epoch).count();
    return JS::Value(static_cast<double>(milliseconds));
}

JS_DEFINE_NATIVE_FUNCTION(AgentObject::sleep)
{
    auto milliseconds = TRY(vm.argument(0).to_i32(global_object));
    ::usleep(milliseconds * 1000);
    return JS::js_undefined();
}
