# -*- coding: utf-8 -*-
#
# Simple vertex to edge reduction.
#
# ```python
# for e in edges(mesh):
#     out = sum(in[v] for v in vertices(e))
# ```

import os
import sys
import types
from gtc_unstructured.frontend.built_in_types import SparseField

from gtc_unstructured.frontend.frontend import GTScriptCompilationTask
from gtc_unstructured.frontend.gtscript import (
    FORWARD,
    Edge,
    Vertex,
    Field,
    computation,
    Connectivity,
    location,
)
from gtc_unstructured.irs.common import DataType
from gtc_unstructured.irs.icon_bindings_codegen import IconBindingsCodegen
from gtc_unstructured.irs.usid_codegen import UsidGpuCodeGenerator, UsidNaiveCodeGenerator

E2V = types.new_class("E2V", (Connectivity[Edge, Vertex, 4, False],))
dtype = DataType.FLOAT64


def icon_sparse_diamond(
    e2v: E2V,
    e_field: Field[Edge, dtype],
    v_field: Field[Vertex, dtype],
    primal_normal: SparseField[E2V, dtype],
):
    with computation(FORWARD), location(Edge) as edge:
        e_field[edge] = sum(v_field[v] * primal_normal[edge, v] for v in e2v[edge])


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "unaive"

    if mode == "unaive":
        code_generator = UsidNaiveCodeGenerator
        extension = ".cc"
    else:  # 'ugpu':
        code_generator = UsidGpuCodeGenerator
        extension = ".cu"

    compilation_task = GTScriptCompilationTask(icon_sparse_diamond)
    generated_code = compilation_task.generate(
        debug=False, code_generator=code_generator
    )

    print(generated_code)
    output_file = (
        os.path.dirname(os.path.realpath(__file__)) +
        "/generated_icon_sparse_diamond_" + mode + ".hpp"
    )
    with open(output_file, "w+") as output:
        output.write(generated_code)

    icon_bindings = IconBindingsCodegen().apply(compilation_task.gtir, generated_code)
    print(icon_bindings)
    output_file = (
        os.path.dirname(os.path.realpath(__file__)) + "/generated_icon_sparse_diamond" + extension
    )
    with open(output_file, "w+") as output:
        output.write(icon_bindings)


if __name__ == "__main__":
    main()
