/*
 * Copyright (c) 2021, Linus Groh <linusg@serenityos.org>
 *
 * SPDX-License-Identifier: MIT
 */

#include "IsHTMLDDA.h"
#include <LibJS/Runtime/GlobalObject.h>

IsHTMLDDA::IsHTMLDDA(JS::GlobalObject& global_object)
    // NativeFunction without prototype is currently not possible (only due to the lack of a ctor that supports it)
    : JS::NativeFunction("IsHTMLDDA", *global_object.function_prototype())
{
}

JS::ThrowCompletionOr<JS::Value> IsHTMLDDA::call()
{
    auto& vm = this->vm();
    if (vm.argument_count() == 0)
        return JS::js_null();
    if (vm.argument(0).is_string() && vm.argument(0).as_string().string().is_empty())
        return JS::js_null();
    // Not sure if this really matters, INTERPRETING.md simply says:
    // * IsHTMLDDA - (present only in implementations that can provide it) an object that:
    //   a. has an [[IsHTMLDDA]] internal slot, and
    //   b. when called with no arguments or with the first argument "" (an empty string) returns null.
    return JS::js_undefined();
}

JS::ThrowCompletionOr<JS::Object*> IsHTMLDDA::construct(JS::FunctionObject&)
{
    // Not sure if we need to support construction, but ¯\_(ツ)_/¯
    auto& vm = this->vm();
    auto& global_object = this->global_object();
    return vm.throw_completion<JS::TypeError>(global_object, JS::ErrorType::NotAConstructor, "IsHTMLDDA");
}
