import warnings

import numpy as np
import torch

from cirkit.einet._EinsumLayer import (
    CPEinsumLayer,
    CPSharedEinsumLayer,
    EinsumMixingLayer,
    HCPTEinsumLayer,
    HCPTLoLoEinsumLayer,
    HCPTLoLoSharedEinsumLayer,
    HCPTSharedEinsumLayer,
    RescalEinsumLayer,
)
from cirkit.einet._leaf_layer import FactorizedLeafLayer
from cirkit.region_graph import graph as Graph

LAYER_TYPES = ["hcpt-lolo-shared", "hcpt-lolo", "rescal", "cp-shared", "hcpt", "hcpt-shared", "cp"]


class LoRaEinNetwork(torch.nn.Module):

    def __init__(self, graph, args):
        # internal layers
        for c, layer in enumerate(self.graph_layers[1:]):
            if c % 2 == 0:  # product layer, that's a partition layer in the graph

                num_sums = set([n.num_dist for p in layer for n in graph.pred[p]])
                if len(num_sums) != 1:
                    raise AssertionError(f"For internal {c} there are {len(num_sums)} nums sums")
                num_sums = list(num_sums)[0]

                layer_type: str = str.lower(self.args.layer_type)
                if layer_type == "hcpt":
                    einet_layers.append(HCPTEinsumLayer(self.graph, layer, einet_layers,
                                                        prod_exp=self.args.prod_exp, k=next(k)))
                elif layer_type == "hcpt-shared":
                    einet_layers.append(HCPTSharedEinsumLayer(self.graph, layer, einet_layers,
                                                              prod_exp=self.args.prod_exp, k=next(k)))
                elif layer_type == "cp":
                    if num_sums > 1:
                        einet_layers.append(CPEinsumLayer(self.graph, layer, einet_layers,
                                                          r=self.args.r,
                                                          prod_exp=self.args.prod_exp, k=next(k)))
                    else:
                        einet_layers.append(RescalEinsumLayer(self.graph, layer, einet_layers, k=next(k)))
                elif layer_type == "cp-shared":
                    if num_sums > 1:
                        einet_layers.append(CPSharedEinsumLayer(self.graph, layer, einet_layers,
                                                                r=self.args.r,
                                                                prod_exp=self.args.prod_exp, k=next(k)))
                    else:
                        einet_layers.append(RescalEinsumLayer(self.graph, layer, einet_layers, k=next(k)))
                elif layer_type == "rescal":
                    if self.args.prod_exp:
                        warnings.warn("Rescal has numerical properties of prod_exp False")
                    einet_layers.append(RescalEinsumLayer(self.graph, layer, einet_layers, k=next(k)))
                elif layer_type == "hcpt-lolo":
                    if num_sums > 1:
                        einet_layers.append(HCPTLoLoEinsumLayer(self.graph, layer,
                                                                einet_layers,
                                                                r=self.args.r,
                                                                prod_exp=self.args.prod_exp, k=next(k)))
                    else:
                        einet_layers.append(HCPTEinsumLayer(self.graph, layer, einet_layers,
                                                            prod_exp=self.args.prod_exp, k=next(k)))

                elif layer_type == "hcpt-lolo-shared":
                    if num_sums > 1:
                        einet_layers.append(HCPTLoLoSharedEinsumLayer(self.graph, layer,
                                                                      einet_layers,
                                                                      r=self.args.r,
                                                                      prod_exp=self.args.prod_exp,
                                                                      k=next(k)))
                    else:
                        einet_layers.append(HCPTEinsumLayer(self.graph, layer, einet_layers,
                                                            prod_exp=self.args.prod_exp, k=next(k)))
                else:
                    raise AssertionError("Unknown layer type")

            else:  # sum layer, that's a region layer in the graph
                # the Mixing layer is only for regions which have multiple partitions as children.
                multi_sums = [n for n in layer if len(graph.succ[n]) > 1]
                if multi_sums:
                    einet_layers.append(EinsumMixingLayer(graph, multi_sums, einet_layers[-1]))

    def em_set_hyperparams(self, online_em_frequency, online_em_stepsize, purge=True):
        for l in self.einet_layers:
            l.em_set_hyperparams(online_em_frequency, online_em_stepsize, purge)

    def em_process_batch(self):
        for l in self.einet_layers:
            l.em_process_batch()

    def em_update(self):
        for l in self.einet_layers:
            l.em_update()


def check_network_parameters(einet: LoRaEinNetwork):

    for n, layer in enumerate(einet.einet_layers):
        if type(layer) == FactorizedLeafLayer:
            continue
        else:
            clamp_value = layer.clamp_value
            for par in layer.parameters():
                if torch.isinf(par).any():
                    raise AssertionError(f"Inf parameter at {n}, {type(layer)}")
                if torch.isnan(par).any():
                    raise AssertionError(f"NaN parameter at {n}, {type(layer)}")
                if not torch.all(par >= clamp_value):
                    raise AssertionError(f"Parameter less than clamp value at {n}, {type(layer)}")

