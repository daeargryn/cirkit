import functools
import itertools
from typing import cast

import numpy as np
import pytest
import torch
from scipy import integrate

import cirkit.symbolic.functional as SF
from cirkit.backend.torch.circuits import TorchCircuit
from cirkit.backend.torch.compiler import TorchCompiler
from cirkit.symbolic.layers import PolynomialLayer
from tests.floats import allclose, isclose
from tests.symbolic.test_utils import (
    build_bivariate_monotonic_structured_cpt_pc,
    build_multivariate_monotonic_structured_cpt_pc,
)


@pytest.mark.parametrize(
    "semiring,fold,optimize,normalized,num_products",
    itertools.product(
        ["sum-product", "lse-sum"], [False, True], [False, True], [False, True], [2, 3, 4]
    ),
)
def test_compile_product_integrate_pc_categorical(
    semiring: str, fold: bool, optimize: bool, normalized: bool, num_products: int
):
    compiler = TorchCompiler(semiring=semiring, fold=fold, optimize=optimize)
    scs, tcs = [], []
    last_sc = None
    for i in range(num_products):
        sci = build_multivariate_monotonic_structured_cpt_pc(
            num_units=2 + i, input_layer="bernoulli", normalized=normalized
        )
        tci = compiler.compile(sci)
        scs.append(sci)
        tcs.append(tci)
        last_sc = sci if i == 0 else SF.multiply(last_sc, sci)
    tc: TorchCircuit = compiler.compile(last_sc)
    int_sc = SF.integrate(last_sc)
    int_tc = compiler.compile(int_sc)

    # Test the partition function value
    z = int_tc()
    assert z.shape == (1, 1)
    z = z.squeeze()
    if normalized:
        if semiring == "sum-product":
            assert 0.0 < z.item() < 1.0
        elif semiring == "lse-sum":
            assert -np.inf < z.item() < 0.0
    worlds = torch.tensor(list(itertools.product([0, 1], repeat=tc.num_variables))).unsqueeze(
        dim=-2
    )
    scores = tc(worlds)
    assert scores.shape == (2**tc.num_variables, 1, 1)
    scores = scores.squeeze()
    assert isclose(compiler.semiring.sum(scores, dim=0), int_tc())

    # Test the products of the circuits evaluated over all possible assignments
    each_tc_scores = torch.stack([tci(worlds).squeeze() for tci in tcs], dim=0)
    assert allclose(compiler.semiring.prod(each_tc_scores, dim=0), scores)


@pytest.mark.slow
def test_compile_product_integrate_pc_gaussian():
    compiler = TorchCompiler(semiring="lse-sum", fold=True, optimize=True)
    scs, tcs = [], []
    last_sc = None
    num_products = 3
    for i in range(num_products):
        sci = build_bivariate_monotonic_structured_cpt_pc(
            num_units=2 + i, input_layer="gaussian", normalized=False
        )
        tci = compiler.compile(sci)
        scs.append(sci)
        tcs.append(tci)
        last_sc = sci if i == 0 else SF.multiply(last_sc, sci)
    tc: TorchCircuit = compiler.compile(last_sc)
    int_sc = SF.integrate(last_sc)
    int_tc = compiler.compile(int_sc)

    # Test the products of the circuits evaluated over _some_ possible assignments
    xs = torch.linspace(-5, 5, steps=16)
    ys = torch.linspace(-5, 5, steps=16)
    points = torch.stack(torch.meshgrid(xs, ys, indexing="xy"), dim=1).view(-1, 1, 2)
    scores = tc(points)
    scores = scores.squeeze()
    each_tc_scores = torch.stack([tci(points).squeeze() for tci in tcs], dim=0)
    assert allclose(torch.sum(each_tc_scores, dim=0), scores)

    # Test the integral of the circuit (using a quadrature rule)
    z = int_tc()
    assert z.shape == (1, 1)
    z = z.squeeze()
    df = lambda y, x: torch.exp(tc(torch.Tensor([[[x, y]]]))).squeeze()
    int_a, int_b = -np.inf, np.inf
    ig, err = integrate.dblquad(df, int_a, int_b, int_a, int_b)
    assert np.isclose(ig, torch.exp(z).item(), atol=1e-15)


# TODO: semiring="complex-lse-sum"?
@pytest.mark.parametrize(
    "semiring,fold,optimize,num_products",
    itertools.product(["sum-product"], [False, True], [False, True], [2, 3, 4]),
)
def test_compile_product_pc_polynomial(
    semiring: str, fold: bool, optimize: bool, num_products: int
) -> None:
    compiler = TorchCompiler(semiring=semiring, fold=fold, optimize=optimize)
    scs, tcs = [], []
    for i in range(num_products):
        sci = build_multivariate_monotonic_structured_cpt_pc(
            num_units=2 + i, input_layer="polynomial"
        )
        tci = compiler.compile(sci)
        scs.append(sci)
        tcs.append(tci)

    sc = functools.reduce(SF.multiply, scs)
    num_variables = sc.num_variables
    degp1 = cast(PolynomialLayer, next(sc.inputs)).degree + 1
    tc: TorchCircuit = compiler.compile(sc)

    inputs = (
        torch.tensor(0.0)  # Get default float dtype.
        .new_tensor(  # degp1**D should be able to determine the coeffs.
            list(itertools.product(range(degp1), repeat=num_variables))  # type: ignore[misc]
        )
        .unsqueeze(dim=-2)
        .requires_grad_()
    )  # shape (B, C=1, D=num_variables).

    zs = torch.stack([tci(inputs) for tci in tcs], dim=0)
    # shape num_prod * (B, num_out=1, num_cls=1).
    assert zs.shape == (num_products, inputs.shape[0], 1, 1)
    zs = zs.squeeze()  # shape (num_prod, B).

    # Test the partition function value
    z = tc(inputs)
    assert z.shape == (inputs.shape[0], 1, 1)  # shape (B, num_out=1, num_cls=1).
    z = z.squeeze()  # shape (B,).

    assert allclose(compiler.semiring.prod(zs, dim=0), z)


# TODO: semiring="complex-lse-sum"?
# TODO: test high-order?
@pytest.mark.parametrize(
    "semiring,fold,optimize", itertools.product(["sum-product"], [False, True], [False, True])
)
def test_compile_differentiate_pc_polynomial(semiring: str, fold: bool, optimize: bool) -> None:
    compiler = TorchCompiler(semiring=semiring, fold=fold, optimize=optimize)
    sc = build_multivariate_monotonic_structured_cpt_pc(input_layer="polynomial")
    num_variables = sc.num_variables

    diff_sc = SF.differentiate(sc, order=1)
    diff_tc: TorchCircuit = compiler.compile(diff_sc)
    assert isinstance(diff_tc, TorchCircuit)
    tc: TorchCircuit = compiler.get_compiled_circuit(sc)
    assert isinstance(tc, TorchCircuit)

    inputs = (
        torch.tensor([[0.0] * num_variables, range(num_variables)])  # type: ignore[misc]
        .unsqueeze(dim=-2)
        .requires_grad_()
    )  # shape (B=2, C=1, D=num_variables).

    with torch.enable_grad():
        output = tc(inputs)
    assert output.shape == (2, 1, 1)  # shape (B=2, num_out=1, num_cls=1).
    (grad_autodiff,) = torch.autograd.grad(
        output, inputs, torch.ones_like(output)
    )  # shape (B=2, C=1, D=num_variables).

    grad = diff_tc(inputs)
    assert grad.shape == (2, num_variables + 1, 1)  # shape (B=2, num_out=1*(D*C+1), num_cls=1).
    # shape (B=2, num_out=D, num_cls=1) -> (B=2, C=1, D=num_variables).
    grad = grad[:, :-1, :].movedim(1, 2)
    # TODO: what if num_cls!=1?
    if semiring == "sum-product":
        assert allclose(grad, grad_autodiff)
    elif semiring == "complex-lse-sum":
        # TODO: is this correct?
        assert allclose(torch.exp(grad), grad_autodiff)
    else:
        assert False
