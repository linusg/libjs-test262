/*
 * Copyright (c) 2021-2022, Linus Groh <linusg@serenityos.org>
 *
 * SPDX-License-Identifier: MIT
 */

#include "AgentObject.h"
#include <AK/Time.h>
#include <LibJS/Runtime/GlobalObject.h>
#include <LibJS/Runtime/Object.h>
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
    auto time = Time::now_monotonic();
    auto milliseconds = time.to_milliseconds();
    return JS::Value(static_cast<double>(milliseconds));
}

JS_DEFINE_NATIVE_FUNCTION(AgentObject::sleep)
{
    auto milliseconds = TRY(vm.argument(0).to_i32(global_object));
    ::usleep(milliseconds * 1000);
    return JS::js_undefined();
}
