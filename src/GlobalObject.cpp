/*
 * Copyright (c) 2021, Linus Groh <linusg@serenityos.org>
 *
 * SPDX-License-Identifier: MIT
 */

#include "GlobalObject.h"
#include "$262Object.h"
#include "AgentObject.h"
#include <AK/Format.h>
#include <LibJS/Heap/Cell.h>
#include <LibJS/Runtime/GlobalObject.h>
#include <LibJS/Runtime/VM.h>

void GlobalObject::initialize_global_object()
{
    Base::initialize_global_object();

    m_$262 = vm().heap().allocate<$262Object>(*this, *this);

    // https://github.com/tc39/test262/blob/master/INTERPRETING.md#host-defined-functions
    u8 attr = JS::Attribute::Writable | JS::Attribute::Configurable;
    define_native_function("print", print, 1, attr);
    define_direct_property("$262", m_$262, attr);
}

void GlobalObject::visit_edges(JS::Cell::Visitor& visitor)
{
    Base::visit_edges(visitor);
    visitor.visit(m_$262);
}

JS_DEFINE_NATIVE_FUNCTION(GlobalObject::print)
{
    auto string = TRY_OR_DISCARD(vm.argument(0).to_string(global_object));
    outln("{}", string);
    return JS::js_undefined();
}
