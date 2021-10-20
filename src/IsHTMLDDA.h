/*
 * Copyright (c) 2021, Linus Groh <linusg@serenityos.org>
 *
 * SPDX-License-Identifier: MIT
 */

#pragma once

#include <LibJS/Runtime/NativeFunction.h>

class IsHTMLDDA final : public JS::NativeFunction {
    JS_OBJECT(IsHTMLDDA, JS::NativeFunction);

public:
    explicit IsHTMLDDA(JS::GlobalObject&);
    virtual ~IsHTMLDDA() override = default;

    virtual JS::ThrowCompletionOr<JS::Value> call() override;
    virtual JS::ThrowCompletionOr<JS::Object*> construct(JS::FunctionObject& new_target) override;

private:
    virtual bool has_constructor() const override { return true; }
    virtual bool is_htmldda() const override { return true; }
};
