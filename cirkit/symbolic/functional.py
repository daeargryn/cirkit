from collections import defaultdict
from contextvars import ContextVar
from typing import Dict, Iterable, List, Optional, Union

from cirkit.symbolic.registry import SymOperatorRegistry
from cirkit.symbolic.sym_circuit import SymCircuit, SymCircuitOperation, SymCircuitOperator
from cirkit.symbolic.sym_layers import (
    SymInputLayer,
    SymLayer,
    SymLayerOperation,
    SymLayerOperator,
    SymProdLayer,
    SymSumLayer,
)
from cirkit.utils import Scope
from cirkit.utils.exceptions import StructuralPropertyError

# Context variable containing the symbolic operator registry.
# This is updated when entering a pipeline context.
_SYM_OPERATOR_REGISTRY: ContextVar[SymOperatorRegistry] = ContextVar(
    "_SYM_OPERATOR_REGISTRY", default=SymOperatorRegistry()
)


def integrate(
    sc: SymCircuit,
    scope: Optional[Iterable[int]] = None,
    registry: Optional[SymOperatorRegistry] = None,
) -> SymCircuit:
    # Check for structural properties
    if not sc.is_smooth or not sc.is_decomposable:
        raise StructuralPropertyError(
            "Only smooth and decomposable circuits can be efficiently integrated."
        )

    # Check the variable
    scope = Scope(scope) if scope is not None else sc.scope
    if (scope | sc.scope) != sc.scope:
        raise ValueError(
            "The variables scope to integrate must be a subset of the scope of the circuit"
        )

    # Load the registry from the context, if not specified
    if registry is None:
        registry = _SYM_OPERATOR_REGISTRY.get()

    # Mapping the symbolic circuit layers with the layers of the new circuit to build
    map_layers: Dict[SymLayer, SymLayer] = {}

    # For each new layer, keep track of (i) its inputs and (ii) the layers it feeds
    in_layers: Dict[SymLayer, List[SymLayer]] = defaultdict(list)
    out_layers: Dict[SymLayer, List[SymLayer]] = defaultdict(list)

    for sl in sc.layers:
        # Input layers get integrated over
        if isinstance(sl, SymInputLayer) and sl.scope & scope:
            if not (sl.scope <= scope):
                raise NotImplementedError(
                    "Multivariate integration of proper subsets of variables is not implemented"
                )
            # Retrieve the integration rule from the registry and apply it
            if registry.has_rule(SymLayerOperator.INTEGRATION, type(sl)):
                func = registry.retrieve_rule(SymLayerOperator.INTEGRATION, type(sl))
            else:  # Use a fallback rule that is not a specialized one
                func = registry.retrieve_rule(SymLayerOperator.INTEGRATION, SymInputLayer)
            map_layers[sl] = func(sl)
        else:  # Sum/product layers are simply copied
            assert isinstance(sl, (SymSumLayer, SymProdLayer))
            new_sl_inputs = [map_layers[isl] for isl in sc.layer_inputs(sl)]
            new_sl: Union[SymSumLayer, SymProdLayer] = type(sl)(
                sl.scope,
                sl.num_units,
                arity=sl.arity,
                operation=SymLayerOperation(operator=SymLayerOperator.NOP, operands=(sl,)),
            )
            map_layers[sl] = new_sl
            in_layers[new_sl] = new_sl_inputs
            for isl in new_sl_inputs:
                out_layers[isl] = new_sl_inputs

    # Construct the integral symbolic circuit and set the integration operation metadata
    return SymCircuit(
        sc.scope,
        list(map_layers.values()),
        in_layers,
        out_layers,
        operation=SymCircuitOperation(
            operator=SymCircuitOperator.INTEGRATION,
            operands=(sc,),
            metadata=dict(scope=scope),
        ),
    )


def multiply(
    lhs_sc: SymCircuit, rhs_sc: SymCircuit, registry: Optional[SymOperatorRegistry] = None
) -> SymCircuit:
    if not lhs_sc.is_compatible(rhs_sc):
        raise StructuralPropertyError(
            "Only compatible circuits can be multiplied into decomposable circuits."
        )
    ...


def differentiate(sc: SymCircuit, registry: Optional[SymOperatorRegistry] = None) -> SymCircuit:
    if not sc.is_smooth or not sc.is_decomposable:
        raise StructuralPropertyError(
            "Only smooth and decomposable circuits can be efficiently differentiated."
        )
    ...
