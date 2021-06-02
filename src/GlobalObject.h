/*
 * Copyright (c) 2021, Linus Groh <linusg@serenityos.org>
 *
 * SPDX-License-Identifier: MIT
 */

#pragma once

#include "$262Object.h"
#include <LibJS/Runtime/GlobalObject.h>

class GlobalObject final : public JS::GlobalObject {
    JS_OBJECT(GlobalObject, JS::GlobalObject);

public:
    GlobalObject() = default;
    virtual void initialize_global_object() override;
    virtual ~GlobalObject() override = default;

private:
    virtual void visit_edges(Visitor&) override;

    $262Object* m_$262 { nullptr };

    JS_DECLARE_NATIVE_FUNCTION(print);
};
