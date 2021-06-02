/*
 * Copyright (c) 2021, Linus Groh <linusg@serenityos.org>
 *
 * SPDX-License-Identifier: MIT
 */

#pragma once

#include <LibJS/Runtime/GlobalObject.h>
#include <LibJS/Runtime/Object.h>

class AgentObject final : public JS::Object {
    JS_OBJECT(AgentObject, JS::Object);

public:
    AgentObject(JS::GlobalObject&);
    virtual void initialize(JS::GlobalObject&) override;
    virtual ~AgentObject() override = default;

private:
    JS_DECLARE_NATIVE_FUNCTION(monotonic_now);
    JS_DECLARE_NATIVE_FUNCTION(sleep);
};
