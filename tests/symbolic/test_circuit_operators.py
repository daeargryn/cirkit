import itertools
from typing import Iterable, Tuple, TypeVar

import pytest

import cirkit.symbolic.functional as SF
from cirkit.symbolic.circuit import are_compatible
from cirkit.symbolic.layers import (
    CategoricalLayer,
    DenseLayer,
    EvidenceLayer,
    GaussianLayer,
    HadamardLayer,
    LogPartitionLayer,
    PolynomialLayer,
)
from cirkit.symbolic.parameters import (
    ConjugateParameter,
    KroneckerParameter,
    PolynomialDifferential,
    ReferenceParameter,
    TensorParameter,
)
from cirkit.utils.scope import Scope
from tests.symbolic.test_utils import build_multivariate_monotonic_structured_cpt_pc


@pytest.mark.parametrize(
    "num_units,input_layer",
    itertools.product([1, 3], ["bernoulli", "gaussian"]),
)
def test_evidence_circuit(num_units: int, input_layer: str):
    sc = build_multivariate_monotonic_structured_cpt_pc(
        num_units=num_units, input_layer=input_layer
    )
    obs = {4: 1 if input_layer == "bernoulli" else 1.23}
    evi_sc = SF.evidence(sc, obs=obs)
    assert evi_sc.scope == Scope([0, 1, 2, 3])
    assert evi_sc.is_smooth
    assert evi_sc.is_decomposable
    assert evi_sc.is_structured_decomposable
    assert not evi_sc.is_omni_compatible
    assert len(list(evi_sc.inputs)) == len(list(sc.inputs))
    evi_layers = [l for l in evi_sc.inputs if evi_sc.layer_scope(l) == Scope([])]
    assert len(evi_layers) == 1
    evi_layer = evi_layers[0]
    assert isinstance(evi_layer, EvidenceLayer)
    assert isinstance(
        evi_layer.layer, CategoricalLayer if input_layer == "bernoulli" else GaussianLayer
    )
    assert evi_layer.observation.shape == (1, 1)
    assert len(list(evi_sc.inner_layers)) == len(list(sc.inner_layers))


@pytest.mark.parametrize(
    "num_units,input_layer",
    itertools.product([1, 3], ["bernoulli", "gaussian"]),
)
def test_integrate_circuit(num_units: int, input_layer: str):
    sc = build_multivariate_monotonic_structured_cpt_pc(
        num_units=num_units, input_layer=input_layer
    )
    int_sc = SF.integrate(sc)
    assert int_sc.is_smooth
    assert int_sc.is_decomposable
    assert int_sc.is_structured_decomposable
    assert not int_sc.scope
    assert len(list(int_sc.inputs)) == len(list(sc.inputs))
    assert all(isinstance(isl, LogPartitionLayer) for isl in int_sc.inputs)
    assert len(list(int_sc.inner_layers)) == len(list(sc.inner_layers))


@pytest.mark.parametrize(
    "num_units,input_layer",
    itertools.product([1, 3], ["bernoulli", "gaussian", "polynomial"]),
)
def test_multiply_circuits(num_units: int, input_layer: str):
    sc1 = build_multivariate_monotonic_structured_cpt_pc(
        num_units=num_units, input_layer=input_layer
    )
    sc2 = build_multivariate_monotonic_structured_cpt_pc(
        num_units=num_units * 2 + 1, input_layer=input_layer
    )
    prod_num_units = num_units * (num_units * 2 + 1)
    sc = SF.multiply(sc1, sc2)
    assert are_compatible(sc1, sc) and are_compatible(sc, sc1)
    assert are_compatible(sc2, sc) and are_compatible(sc, sc2)
    assert len(list(sc.inputs)) == len(list(sc1.inputs))
    assert len(list(sc.inputs)) == len(list(sc2.inputs))
    assert len(list(sc.inner_layers)) == len(list(sc1.inner_layers))
    assert len(list(sc.inner_layers)) == len(list(sc2.inner_layers))
    assert all(l.num_output_units == prod_num_units for l in sc.inputs)
    dense_layers = list(filter(lambda l: isinstance(l, DenseLayer), sc.inner_layers))
    assert all(isinstance(l.weight.output, KroneckerParameter) for l in dense_layers)
    assert all(
        l.weight.shape == (prod_num_units, prod_num_units)
        for l in dense_layers
        if sc.layer_outputs(l)
    )
    prod_layers = list(filter(lambda l: not isinstance(l, DenseLayer), sc.inner_layers))
    assert all(isinstance(l, HadamardLayer) for l in prod_layers)
    assert all(l.num_input_units == prod_num_units for l in dense_layers if sc.layer_outputs(l))
    assert all(l.num_output_units == prod_num_units for l in dense_layers if sc.layer_outputs(l))
    # Additional check of degree for polynomial
    if input_layer == "polynomial":
        for in_1, in_2, in_prod in zip(sc1.inputs, sc2.inputs, sc.inputs):
            assert isinstance(in_1, PolynomialLayer)
            assert isinstance(in_2, PolynomialLayer)
            assert isinstance(in_prod, PolynomialLayer)
            assert in_prod.degree == in_1.degree + in_2.degree


@pytest.mark.parametrize(
    "num_units,input_layer",
    itertools.product([1, 3], ["bernoulli", "gaussian"]),
)
def test_multiply_integrate_circuits(num_units: int, input_layer: str):
    sc1 = build_multivariate_monotonic_structured_cpt_pc(
        num_units=num_units, input_layer=input_layer
    )
    sc2 = build_multivariate_monotonic_structured_cpt_pc(
        num_units=num_units * 2 + 1, input_layer=input_layer
    )
    prod_num_units = num_units * (num_units * 2 + 1)
    sc = SF.multiply(sc1, sc2)
    int_sc = SF.integrate(sc)
    assert not int_sc.scope
    assert len(list(int_sc.inputs)) == len(list(sc.inputs))
    assert all(isinstance(isl, LogPartitionLayer) for isl in int_sc.inputs)
    assert len(list(int_sc.inner_layers)) == len(list(sc.inner_layers))
    dense_layers = list(filter(lambda l: isinstance(l, DenseLayer), int_sc.inner_layers))
    assert all(isinstance(l.weight.output, KroneckerParameter) for l in dense_layers)
    assert all(
        l.weight.shape == (prod_num_units, prod_num_units)
        for l in dense_layers
        if sc.layer_outputs(l)
    )
    prod_layers = list(filter(lambda l: not isinstance(l, DenseLayer), sc.inner_layers))
    assert all(isinstance(l, HadamardLayer) for l in prod_layers)
    assert all(l.num_input_units == prod_num_units for l in dense_layers if sc.layer_outputs(l))
    assert all(l.num_output_units == prod_num_units for l in dense_layers if sc.layer_outputs(l))


@pytest.mark.parametrize(
    "num_units,input_layer",
    itertools.product([1, 3], ["bernoulli", "gaussian", "polynomial"]),
)
def test_conjugate_circuit(num_units: int, input_layer: str):
    sc1 = build_multivariate_monotonic_structured_cpt_pc(
        num_units=num_units, input_layer=input_layer
    )
    sc = SF.conjugate(sc1)
    assert len(list(sc.inputs)) == len(list(sc.inputs))
    assert len(list(sc.inner_layers)) == len(list(sc.inner_layers))
    dense_layers = list(filter(lambda l: isinstance(l, DenseLayer), sc.inner_layers))
    assert all(isinstance(l.weight.output, ConjugateParameter) for l in dense_layers)
    assert all(
        l.weight.shape == (num_units, num_units) for l in dense_layers if sc.layer_outputs(l)
    )
    prod_layers = list(filter(lambda l: not isinstance(l, DenseLayer), sc.inner_layers))
    assert all(isinstance(l, HadamardLayer) for l in prod_layers)
    assert all(l.num_input_units == num_units for l in dense_layers if sc.layer_outputs(l))
    assert all(l.num_output_units == num_units for l in dense_layers if sc.layer_outputs(l))


_T_co = TypeVar("_T_co", covariant=True)  # TODO: for _batched. move together


# TODO: this can be made public and moved to utils, might be used elsewhere.
# itertools.batched introduced in 3.12
def _batched(iterable: Iterable[_T_co], n: int) -> Iterable[Tuple[_T_co, ...]]:
    if n < 1:
        raise ValueError("n must be at least one")
    iterator = iter(iterable)
    while batch := tuple(itertools.islice(iterator, n)):
        yield batch


@pytest.mark.parametrize("num_units", [1, 3])
def test_differentiate_circuit(num_units: int) -> None:
    sc = build_multivariate_monotonic_structured_cpt_pc(
        num_units=num_units, input_layer="polynomial"
    )
    diff_sc = SF.differentiate(sc)
    assert diff_sc.is_smooth
    assert diff_sc.is_decomposable
    assert diff_sc.is_structured_decomposable
    assert not diff_sc.is_omni_compatible
    sc_inputs = list(sc.inputs)
    diff_inputs = list(diff_sc.inputs)
    sc_inner = list(sc.inner_layers)
    diff_inner = list(diff_sc.inner_layers)
    assert len(diff_inputs) == len(sc_inputs) * 2  # diff and self
    assert all(
        isinstance(dl.coeff.output, PolynomialDifferential)
        and isinstance(sl.coeff.output, ReferenceParameter)
        for dl, sl in _batched(diff_inputs, 2)
    )
    assert len(diff_inner) == sum(len(sc.layer_scope(l)) for l in sc_inner) + len(sc_inner)
    dense_layers = list(filter(lambda l: isinstance(l, DenseLayer), diff_sc.inner_layers))
    assert dense_layers
    # TODO: should we keep more info for diff layer ordering? i.e. testing order wrt each var
