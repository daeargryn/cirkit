from torch import Tensor

from cirkit.pipeline import PipelineContext
from cirkit.symbolic.symb_circuit import SymbCircuit
from cirkit.symbolic.symb_layers import SymbCategoricalLayer, SymbDenseLayer, SymbKroneckerLayer, SymbMixingLayer
from cirkit.symbolic.symb_params import SymbSoftplus, SymbParameter, SymbSoftmax
from cirkit.templates.region_graph.algorithms import FullyFactorized, QuadTree
from cirkit.utils import Scope


def categorical_layer_factory(
        scope: Scope,
        num_variables: int,
        num_units: int,
        num_channels: int
) -> SymbCategoricalLayer:
    return SymbCategoricalLayer(
        scope, num_variables, num_units, num_channels, num_categories=256,
        param_factory=lambda shape: SymbSoftmax(SymbParameter(*shape), axis=-1)
    )


def dense_layer_factory(
        scope: Scope,
        num_input_units: int,
        num_output_units: int,
) -> SymbDenseLayer:
    return SymbDenseLayer(
        scope, num_input_units, num_output_units,
        param_factory=lambda shape: SymbSoftplus(SymbParameter(*shape))
    )


def hadamard_layer_factory(scope: Scope, num_input_units: int, arity: int):
    return SymbKroneckerLayer(scope, num_input_units, arity)


def mixing_layer_factory(scope: Scope, num_units: int, arity: int):
    return SymbMixingLayer(
        scope, num_units, arity,
        param_factory=lambda shape: SymbSoftplus(SymbParameter(*shape))
    )


def example_simple_pc() -> None:
    # Create a region graph
    qt = QuadTree(shape=(28, 28), struct_decomp=True)

    # Instantiate a symbolic circuit from the region graph,
    # by specifying factories that construct symbolic layers
    sc = SymbCircuit.from_region_graph(
        qt, num_input_units=8, num_sum_units=16,
        input_factory=categorical_layer_factory,
        sum_factory=dense_layer_factory,
        prod_factory=hadamard_layer_factory,
        mixing_factory=mixing_layer_factory
    )

    # Given the output of a computational graph over circuits (i.e., the root of the DAG),
    # ctx.compile compiles all the circuits in topological ordering (at least by default)
    # The backend can be specified with a flag, and available optimizations using kwargs.
    # For instance, the backend 'torch' might support the following optimizations:
    # - fold=True  enables folding;
    # - einsum=True  suggests compiling to layers using einsums when possible.
    ctx = PipelineContext(backend='torch', fold=True, einsum=True)
    tc = ctx.compile(sc)
    int_tc = ctx.integrate(tc)   # This is equivalent to 'ctx.compile(integrate(sc))'

    # Do inference or learning with the compiled circuits
    ...


def example_pipeline() -> None:
    # Create two region graphs
    qt = QuadTree(shape=(28, 28), struct_decomp=True)
    ff = FullyFactorized(num_vars=28 * 28)

    # Instantiate two symbolic circuits from the region graphs,
    # by specifying symbolic layers and symbolic parameterizations
    p = SymbCircuit.from_region_graph(
        qt,
        num_input_units=16,
        num_sum_units=16,
        input_cls=SymbCategoricalLayer,
        sum_cls=SymbSumLayer,
        prod_cls=SymbHadamardLayer,
        input_param_cls=SymbSoftmax,
        sum_param_cls=SymbSoftplus,
    )
    q = SymbCircuit.from_region_graph(
        ff,
        num_input_units=16,
        input_cls=SymbCategoricalLayer,
        prod_cls=SymbHadamardLayer,
        input_param_cls=SymbSoftmax,
    )

    # Construct the pipeline
    r = differentiate(q)
    s = multiply(p, r)
    t = integrate(s)

    # Create a pipeline context for compilation
    # Given the output of a computational graph over circuits (i.e., the root of the DAG),
    # ctx.compile compiles all the circuits in topological ordering (at least by default)
    # The backend can be specified with a flag, and available optimizations using kwargs.
    # For instance, the backend 'torch' might support the following optimizations:
    # - fold=True  enables folding;
    # - einsum=True  suggests compiling to layers using einsums when possible.
    ctx = PipelineContext()
    ctx.compile(t, backend="torch", fold=True, einsum=True)

    # Retrieve the compiled tensorized circuits from the pipeline context
    # These circuits are torch modules and share parameters accordingly
    tensorized_r, tensorized_t = ctx[r], ctx[t]

    # Do inference or learning with the compiled circuits
    ...


def example_serialization() -> None:
    ################################ PART 1 ################################

    # Create two region graphs
    qt = QuadTree(shape=(28, 28), struct_decomp=True)
    ff = FullyFactorized(num_vars=28 * 28)

    # Instantiate two symbolic circuits from the region graphs,
    # by specifying symbolic layers and symbolic parameterizations
    p = SymbCircuit.from_region_graph(
        qt,
        num_input_units=16,
        num_sum_units=16,
        input_cls=SymbCategoricalLayer,
        sum_cls=SymbSumLayer,
        prod_cls=SymbHadamardLayer,
        input_param_cls=SymbSoftmax,
        sum_param_cls=SymbSoftplus,
    )
    q = SymbCircuit.from_region_graph(
        ff,
        num_input_units=16,
        input_cls=SymbCategoricalLayer,
        prod_cls=SymbHadamardLayer,
        input_param_cls=SymbSoftmax,
    )

    # Construct the pipeline
    r = differentiate(q)
    s = multiply(p, r)

    # Create a pipeline context for compilation
    # Given the output of a computational graph over circuits (i.e., the root of the DAG),
    # ctx.compile compiles all the circuits in topological ordering (at least by default)
    # The backend can be specified with a flag, and available optimizations using kwargs.
    # For instance, the backend 'torch' might support the following optimizations:
    # - fold=True  enables folding;
    # - einsum=True  suggests compiling to layers using einsums when possible.
    ctx = PipelineContext(backend="torch")
    ctx.compile(s, fold=True, einsum=True)

    # Retrieve the compiled tensorized circuits from the pipeline context
    # These circuits are torch modules and share parameters accordingly
    tensorized_r, tensorized_s = ctx[r], ctx[s]

    # Do inference or learning with the compiled circuits
    ...

    ################################ PART 2 ################################

    # Let's suppose we now want to save this pipeline and load it later
    # Saving a single symbolic/tensorized circuit would not allow us to do other operations later,
    # unless they are the input circuits of the pipeline. This is because we have parameter sharing
    # between circuits, and connections between symbolic representations.
    # For this reason, we can save the pipeline context, which already knows the backed and therefore
    # will use the relevant save routines for that backend.
    # Note that we can save symbolic and tensorized circuits in different files.
    ctx.save("symbolic-pipeline.ckit", "tensorized-circuits.pt")

    # Now, let's load again the context
    ctx = PipelineContext.load("symbolic-pipeline.ckit", "tensorized-circuits.pt")

    # Since we have saved SymbCircuitthe context, we can incrementally operate on circuits and compile them,
    # without losing any useful data structure from previous compilations (e.g., references between layers)
    # That is, we can extend the symbolic pipeline using other operators
    s = ctx[
        "product.0"
    ]  # Let's assume symbolic circuits will have labels or names that the user can set
    t = integrate(s)
    ctx.compile(t)

    # Retrieve the compiled tensorized circuit from the pipeline context
    tensorized_t = ctx[t]

    # Do inference or learning with the compiled circuits
    ...


def example_lib_extension() -> None:
    ################################ PART 1 ################################
    # Create a region graph
    qt = QuadTree(shape=(28, 28), struct_decomp=True)

    # Let's suppose the user wants to introduce a new input layer called 'PolyGaussian',
    # and a new parameterization for that layer called 'PolyGaussianParameter'.
    # Ideally, they have to first create a symbolic token for it, with the hyperparameters they care about.
    # Any input layer will always have the scope, the number of units/channels, and a possibly None operation.
    class SymbPolyGaussianLayer(SymbInputLayer):
        def __init__(
            self,
            scope: Scope,
            num_units: int,
            num_channels: int,
            operation: Optional[SymbLayerOperation] = None,
            *,
            degree: int = 2,
            coeffs: Optional[SymbParameter] = None,
        ):
            super().__init__(scope, num_units, num_channels, operation=operation)
            self.degree = degree
            if coeffs is None:
                coeffs = SymbParameter(shape=(len(self.scope), self.num_channels, self.num_units))
            self.coeffs = coeffs

        # The following two methods specify the protocol for this symbolic token, i.e.,
        # the hyperparameters and the parameters (all in symbolic/non-executable form).

        def forward(self):
            # Dense(Hadamard(x))
            pass
            # Symbolic forward with symbolic primitives?
            # Can we process the symbolic code in forward with metaprogramming?

        @staticmethod
        def hyper_params(self) -> Dict[str, Any]:
            return {"degree": self.degree}

        @staticmethod
        def params(self) -> Dict[str, Any]:
            return {"coeffs": self.coeffs}

    # Let's assume that this new parameterization takes alpha and beta as hyperparameters.
    class SymbPolyGaussianParam(SymbParameterUnary):
        def __init__(self, opd: AbstractSymbParameter, alpha: float, beta: float):
            super().__init__(opd)
            self.alpha = alpha
            self.beta = beta

    # Then, the user must write the executable classes for the above tokens,
    # by using some backend of their choice, e.g., torch
    class PolyGaussianLayer(InputLayer):
        def __init__(
            self,
            num_channels: int,
            num_output_units: int,
            num_vars: int,
            *,
            degree: int,
            weight: Reparameterization,
        ):
            super().__init__(
                num_input_units=num_channels, num_output_units=num_output_units, arity=num_vars
            )
            self.degree = degree
            self.weight = weight

        def polyval(self, p: Tensor, x: Tensor) -> Tensor:
            ...

        def forward(self, x: Tensor) -> Tensor:
            params_exp, params_poly = self.weight()
            # The exponent is always in log-space.
            gaussian = self.polyval(self.params_exp, x)
            if params_poly is None:
                return gaussian
            factor = self.polyval(self.params_poly, x)
            return torch.mul(gaussian, factor)

    class PolyGaussianParam(UnaryReparam):
        def __init__(
            self,
            reparam: Optional[Reparameterization] = None,
            alpha: float = 0.0,
            beta: float = 1.0,
        ):
            super().__init__(reparam=reparam, func=self.forward)
            self.alpha = alpha
            self.beta = beta

        def forward(self) -> Tuple[Tensor, Tensor]:
            ...

        @staticmethod
        def hyper_params(self) -> Dict[str, Any]:
            return {"alpha": self.alpha, "beta": self.beta}

    # Let's suppose the user is too lazy to specify the symbolic classes for the torch modules above.
    # Then, we can have some meta-programming utils to extract them from classes (e.g., torch modules).
    # Ideally, from torch modules, these functions could read the parameters and hyperparameters in the init method.
    # As an alternative, these methods could require the specification of parameter shapes and hyperparameters names as
    # static methods (e.g., hyper_params specified in PolyGaussianParam above).
    symb_polygaussian_cls = symbolic_input_layer_cls(PolyGaussianLayer)
    symb_polygaussian_param_cls = symbolic_parameter_cls(PolyGaussianParam)

    # With these symbolic classes, we are ready to instantiate a couple of symbolic circuits
    p = SymbCircuit.from_region_graph(
        qt,
        num_input_units=16,
        num_sum_units=16,
        input_cls=SymbPolyGaussianLayer,
        sum_cls=SymbSumLayer,
        prod_cls=SymbHadamardLayer,
        input_param_cls=SymbPolyGaussianParam,
        sum_param_cls=SymbSoftplus,
    )
    q = SymbCircuit.from_region_graph(
        qt,
        num_input_units=16,
        num_sum_units=16,
        input_cls=SymbPolyGaussianLayer,
        sum_cls=SymbSumLayer,
        prod_cls=SymbHadamardLayer,
        input_param_cls=SymbPolyGaussianParam,
        sum_param_cls=SymbSoftplus,
    )

    ################################ PART 2 ################################

    # Now, we need to extend the compiler such that it knows that:
    # - SymbPolyGaussianLayer must be compiled into PolyGaussianLayer
    # - SymbPolyGaussianParam must be PolyGaussianParam
    # To do so, we extend the pipeline context by registering new compilation rules.
    ctx = CompilationContext(backend="torch")
    ctx.register_layer_compilation_rule(SymbPolyGaussianLayer, PolyGaussianLayer)
    ctx.register_param_compilation_rule(SymbPolyGaussianParam, PolyGaussianParam)
    ctx.compile(p)
    tens_p = ctx[p]

    # Let's suppose the user want to implement the product between their new layer
    # As usual, it must implement first the symbolic protocol for that.
    # First, we must create the product layer class (if the product is not a closed operation).
    class SymbPolyGaussianProductLayer(SymbInputLayer):
        def __init__(
            self,
            scope: Scope,
            num_units: int,
            num_channels: int,
            operation: SymbLayerOperation,
            *,
            degree: int,
            coeffs: SymbParameter,
        ):
            super().__init__(scope, num_units, num_channels, operation=operation)
            self.degree = degree
            self.coeffs = coeffs

    # Then, we have to implement the symbolic product function
    def poly_gaussian_product(
        lhs: SymbPolyGaussianLayer, rhs: SymbPolyGaussianLayer
    ) -> SymbPolyGaussianLayer:
        # Assume something toy-ish for the product
        assert lhs.scope == rhs.scope
        assert lhs.num_channels == rhs.num_units
        return SymbPolyGaussianLayer(
            lhs.scope,
            lhs.num_units * rhs.num_channels,
            num_channels=lhs.num_channels,
            operation=SymbKronecker(lhs, rhs),  # Record the product operation
            degree=lhs.degree * rhs.degree + 1,
            coeffs=SymbKronecker(lhs.coeffs, rhs.coeffs),
        )

    # Let's assume there is also some torch module implementing the poly gaussian product
    class PolyGaussianProductLayer(InputLayer):
        ...

    # Compute the product, by passing the above function to the registry
    # Perhaps a better way could be a symbolic context that keeps tracks of these registries,
    # akin to the pipeline context but simpler as it does not depend on the backend nor needs to do optimizations
    with PipelineContext() as ctx:
        ctx.add_operation_rule(AbstractSymbLayerOperator.MULTIPLICATION, poly_gaussian_product)
        r = ctx.multiply(p, q)
        tensorized_r = ctx.compile(r, fold=True)

        def folded_product(ctx: PipelineContext, p: SymbCircuit, q: SymbCircuit) -> SymbCircuit:
            assert p.is_compatible(q)
            f_p = ctx.fold(p)
            f_q = ctx.fold(q)
            f_r = folded_multiply(f_p, f_q)
            return f_r

        ctx.add_pipeline_rule(SymbCircuitOperator.MULTIPLICATION, folded_product)

    # Next, we want to materialize such a product.
    # To do so, we register the following compilation rule into the context, and then compile
    # ctx.register_layer_compilation_rule(SymbPolyGaussianProductLayer, PolyGaussianProductLayer)
    ctx.compile(r)
    tens_r = ctx[r]
