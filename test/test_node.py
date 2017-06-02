#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# test_node.py

import numpy as np

from pyphi.network import Network
from pyphi.subsystem import Subsystem
from pyphi.node import Node, expand_node_tpm, generate_nodes


def test_node_init_tpm(s):
    answer = [
        np.array([[[[1., 0.],
                    [0., 0.]]],
                  [[[0., 1.],
                    [1., 1.]]]]),
        np.array([[[[1., 0.]]],
                  [[[0., 1.]]]]),
        np.array([[[[1.],
                    [0.]],
                   [[0.],
                    [1.]]],
                  [[[0.],
                    [1.]],
                   [[1.],
                    [0.]]]])
    ]
    for node in s.nodes:
        assert np.array_equal(node.tpm, answer[node.index])


def test_node_init_inputs(s):
    answer = [
        s.nodes[1:],
        s.nodes[2:3],
        s.nodes[:2]
    ]
    for node in s.nodes:
        assert set(node.inputs) == set(answer[node.index])


def test_node_eq(s):
    assert s.nodes[1] == Node(s.tpm, s.cm, 1, 0, 'B')


def test_node_neq_by_index(s):
    assert s.nodes[0] != Node(s.tpm, s.cm, 1, 0, 'B')


def test_node_neq_by_state(s):
    other_s = Subsystem(s.network, (1, 1, 1), s.node_indices)
    assert other_s.nodes[1] != Node(s.tpm, s.cm, 1, 0, 'B')


def test_repr(s):
    print(repr(s.nodes[0]))


def test_str(s):
    print(str(s.nodes[0]))


def test_expand_tpm():
    tpm = np.array([
        [[0, 1]]
    ])
    answer = np.array([
        [[0, 1],
         [0, 1]],
        [[0, 1],
         [0, 1]]
    ])
    assert np.array_equal(expand_node_tpm(tpm), answer)


def test_generate_nodes(s):
    nodes = generate_nodes(s.tpm, s.cm, s.state)

    node0_tpm = np.array([
        [[[1, 0],
          [0, 0]]],
        [[[0, 1],
          [1, 1]]]
    ])
    assert np.array_equal(nodes[0].tpm, node0_tpm)
    assert nodes[0].input_indices == (1, 2)
    assert nodes[0].inputs == (nodes[1], nodes[2])
    assert nodes[0].output_indices == (2,)
    assert nodes[0].outputs == (nodes[2],)
    assert nodes[0].label == 'n0'

    node1_tpm = np.array([
        [[[1, 0]]],
        [[[0, 1]]]
    ])
    assert np.array_equal(nodes[1].tpm, node1_tpm)
    assert nodes[1].input_indices == (2,)
    assert nodes[1].inputs == (nodes[2],)
    assert nodes[1].output_indices == (0, 2)
    assert nodes[1].outputs == (nodes[0], nodes[2])
    assert nodes[1].label == 'n1'

    node2_tpm = np.array([
        [[[1],
          [0]],
         [[0],
          [1]]],
        [[[0],
          [1]],
         [[1],
          [0]]]
    ])
    assert np.array_equal(nodes[2].tpm, node2_tpm)
    assert nodes[2].input_indices == (0, 1)
    assert nodes[2].inputs == (nodes[0], nodes[1])
    assert nodes[2].output_indices == (0, 1)
    assert nodes[2].outputs == (nodes[0], nodes[1])
    assert nodes[2].label == 'n2'
