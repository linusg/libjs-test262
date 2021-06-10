/*
 * Copyright (c) 2021, Linus Groh <linusg@serenityos.org>
 *
 * SPDX-License-Identifier: MIT
 */

#pragma once

#include "AgentObject.h"
#include <LibJS/Runtime/GlobalObject.h>
#include <LibJS/Runtime/Object.h>

class $262Object final : public JS::Object {
    JS_OBJECT($262Object, JS::Object);

public:
    $262Object(JS::GlobalObject&);
    virtual void initialize(JS::GlobalObject&) override;
    virtual ~$262Object() override = default;

private:
    virtual void visit_edges(Visitor&) override;

    AgentObject* m_agent { nullptr };

    JS_DECLARE_NATIVE_FUNCTION(create_realm);
    JS_DECLARE_NATIVE_FUNCTION(eval_script);
};
