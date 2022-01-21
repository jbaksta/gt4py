# GT4Py Project - GridTools Framework
#
# Copyright (c) 2014-2021, ETH Zurich
# All rights reserved.
#
# This file is part of the GT4Py project and the GridTools framework.
# GT4Py is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or any later
# version. See the LICENSE.txt file at the top-level directory of this
# distribution for a copy of the license or check <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import List, Optional

from eve import NodeTranslator
from functional.ffront import field_operator_ast as foast
from functional.iterator import ir as itir


class AssignResolver(NodeTranslator):
    """
    Inline a sequence of assignments into a final return statement.

    >>> from functional.ffront.func_to_foast import FieldOperatorParser
    >>> from functional.common import Field
    >>>
    >>> float64 = float
    >>>
    >>> def fieldop(inp: Field[..., "float64"]):
    ...     tmp1 = inp
    ...     tmp2 = tmp1
    ...     return tmp2
    >>>
    >>> fieldop_foast_expr = AssignResolver.apply(FieldOperatorParser.apply_to_function(fieldop).body)
    >>> fieldop_foast_expr  # doctest: +ELLIPSIS
    Return(location=..., value=Name(location=..., id='inp'))
    """

    @classmethod
    def apply(
        cls, nodes: List[foast.Expr], *, params: Optional[list[itir.Sym]] = None
    ) -> foast.Expr:
        names: dict[str, foast.Expr] = {}
        parser = cls()
        for node in nodes[:-1]:
            names.update(parser.visit(node, names=names))
        return foast.Return(
            value=parser.visit(nodes[-1].value, names=names), location=nodes[-1].location
        )

    def visit_Assign(
        self,
        node: foast.Assign,
        *,
        names: Optional[dict[str, foast.Expr]] = None,
    ) -> dict[str, itir.Expr]:
        return {node.target.id: self.visit(node.value, names=names)}

    def visit_Name(
        self,
        node: foast.Name,
        *,
        names: Optional[dict[str, foast.Expr]] = None,
    ):
        names = names or {}
        if node.id in names:
            return names[node.id]
        return node


class FieldOperatorLowering(NodeTranslator):
    """
    Lower FieldOperator AST (FOAST) to Iterator IR (ITIR).

    Examples
    --------
    >>> from functional.ffront.func_to_foast import FieldOperatorParser
    >>> from functional.common import Field
    >>>
    >>> float64 = float
    >>>
    >>> def fieldop(inp: Field[..., "float64"]):
    ...    return inp
    >>>
    >>> parsed = FieldOperatorParser.apply_to_function(fieldop)
    >>> lowered = FieldOperatorLowering.apply(parsed)
    >>> type(lowered)
    <class 'functional.iterator.ir.FunctionDefinition'>
    >>> lowered.id
    'fieldop'
    >>> lowered.params
    [Sym(id='inp')]
    >>> lowered.expr
    FunCall(fun=SymRef(id='deref'), args=[SymRef(id='inp')])
    """

    @classmethod
    def apply(cls, node: foast.FieldOperator) -> itir.FunctionDefinition:
        return cls().visit(node)

    def visit_FieldOperator(self, node: foast.FieldOperator, **kwargs) -> itir.FunctionDefinition:
        symtable = node.symtable_
        params = self.visit(node.params, symtable=symtable)
        return itir.FunctionDefinition(
            id=node.id,
            params=params,
            expr=self.body_visit(node.body, params=params, symtable=symtable),
        )

    def body_visit(
        self,
        exprs: List[foast.Expr],
        params: Optional[List[itir.Sym]] = None,
        **kwargs,
    ) -> itir.Expr:
        return self.visit(AssignResolver.apply(exprs), **kwargs)

    def visit_Return(self, node: foast.Return, **kwargs) -> itir.Expr:
        return self.visit(node.value, **kwargs)

    def visit_FieldSymbol(
        self, node: foast.FieldSymbol, *, symtable: dict[str, foast.Symbol], **kwargs
    ) -> itir.Sym:
        return itir.Sym(id=node.id)

    def visit_Name(
        self, node: foast.Name, *, symtable: dict[str, foast.Symbol], **kwargs
    ) -> itir.SymRef:
        if node.id in symtable:
            if isinstance(symtable[node.id], foast.FieldSymbol):
                return itir.FunCall(fun=itir.SymRef(id="deref"), args=[itir.SymRef(id=node.id)])
        return itir.SymRef(id=node.id)

    def visit_Subscript(self, node: foast.Subscript, **kwargs) -> itir.FunCall:
        return itir.FunCall(
            fun=itir.SymRef(id="tuple_get"),
            args=[self.visit(node.value, **kwargs), itir.IntLiteral(value=node.index)],
        )

    def visit_TupleExpr(self, node: foast.TupleExpr, **kwargs) -> itir.FunCall:
        return itir.FunCall(
            fun=itir.SymRef(id="make_tuple"), args=[self.visit(i, **kwargs) for i in node.elts]
        )

    def visit_UnaryOp(self, node: foast.UnaryOp, **kwargs) -> itir.FunCall:
        zero_arg = [itir.IntLiteral(value=0)] if node.op is not foast.UnaryOperator.NOT else []
        return itir.FunCall(
            fun=itir.SymRef(id=node.op.value),
            args=[*zero_arg, self.visit(node.operand, **kwargs)],
        )

    def visit_BinOp(self, node: foast.BinOp, **kwargs) -> itir.FunCall:
        return itir.FunCall(
            fun=itir.SymRef(id=node.op.value),
            args=[self.visit(node.left, **kwargs), self.visit(node.right, **kwargs)],
        )

    def visit_Compare(self, node: foast.Compare, **kwargs) -> itir.FunCall:
        return itir.FunCall(
            fun=itir.SymRef(id=node.op.value),
            args=[self.visit(node.left, **kwargs), self.visit(node.right, **kwargs)],
        )

    def visit_Call(self, node: foast.Call, **kwargs) -> itir.FunCall:
        new_fun = (
            itir.SymRef(id=node.func.id)
            if isinstance(node.func, foast.Name)
            else self.visit(node.func, **kwargs)
        )
        return itir.FunCall(
            fun=new_fun,
            args=[self.visit(arg, **kwargs) for arg in node.args],
        )