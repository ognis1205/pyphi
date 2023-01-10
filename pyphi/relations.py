# relations.py

"""Functions for computing relations among distinctions."""

import warnings
from functools import cached_property

from graphillion import setset

from . import combinatorics, utils
from .compute.parallel import MapReduce
from .conf import config, fallback
from .data_structures import PyPhiFloat
from .models import cmp, fmt
from .models.subsystem import FlatCauseEffectStructure
from .registry import Registry
from .warnings import PyPhiWarning


class RelationFace(frozenset):
    """A set of (potentially) related causes/effects."""

    @cached_property
    def overlap(self):
        """The set of elements that are in the purview of every relatum."""
        return set.intersection(*map(set, self.relata_purviews))

    @cached_property
    def congruent_overlap(self):
        """Return the congruent overlap(s) among the relata.

        These are the common purview elements among the relata whose specified
        states are consistent; that is, the largest subset of the union of the
        purviews such that each relatum specifies the same state for each
        element.
        """
        return set.intersection(*self.relata_units)

    # Alias
    @property
    def purview(self):
        """The purview of the relation face. Alias for ``congruent_overlap``."""
        return self.congruent_overlap

    @property
    def relata_units(self):
        """The cause/effect purview of each cause/effect in this face."""
        return (set(relatum.purview_units) for relatum in self)

    @property
    def relata_purviews(self):
        return (relatum.purview for relatum in self)

    def __bool__(self):
        return bool(self.congruent_overlap)

    def _repr_columns(self):
        return [
            ("Purview", str(sorted(self.purview))),
            ("Relata", len(self)),
        ]

    def __repr__(self):
        # TODO(4.0) refactor into fmt function
        body = "\n".join(fmt.align_columns(self._repr_columns()))
        body = fmt.center(body)
        body += "\n" + fmt.indent(fmt.fmt_relata(self), amount=10)
        body = fmt.header(self.__class__.__name__, body, under_char=fmt.HEADER_BAR_2)
        return fmt.box(body)

    def to_json(self):
        return {"relata": list(self)}

    @classmethod
    def from_json(cls, data):
        return cls(data["relata"])


class Relation(frozenset, cmp.Orderable):
    """A set of relation faces forming the relation among a set of distinctions."""

    @cached_property
    def faces(self):
        mice = FlatCauseEffectStructure(self)
        return frozenset(
            RelationFace((mice[i] for i in combination))
            for combination in _combinations_with_nonempty_congruent_overlap(mice)
        )

    @property
    def num_faces(self):
        return len(self.faces)

    @cached_property
    def purview(self):
        # Special case for self-relations
        if self.is_self_relation:
            distinction = next(iter(self))
            return distinction.cause.purview_units & distinction.effect.purview_units

        return set.intersection(*(distinction.purview_union for distinction in self))

    @property
    def is_self_relation(self):
        return len(self) == 1

    @cached_property
    def phi(self):
        return PyPhiFloat(
            len(self.purview) * min(self.distinction_phi_per_unique_purview_unit())
        )

    def distinction_phi_per_unique_purview_unit(self):
        return (relatum.phi / len(relatum.purview_union) for relatum in self)

    def __bool__(self):
        return utils.is_positive(self.phi)

    def order_by(self):
        return self.phi

    def _repr_columns(self):
        return [
            (fmt.SMALL_PHI + "_r", self.phi),
            ("Purview", str(sorted(self.purview))),
            ("#(faces)", self.num_faces),
        ]

    def __repr__(self):
        # TODO(4.0) refactor into fmt function
        body = "\n".join(fmt.align_columns(self._repr_columns()))
        body = fmt.center(body)
        body = fmt.header(self.__class__.__name__, body, under_char=fmt.HEADER_BAR_2)
        return fmt.box(body)


DEFAULT_RELATION_CHUNKSIZE = 2**14
DEFAULT_RELATION_SEQUENTIAL_THRESHOLD = 2**12


def all_relations(distinctions, min_degree=2, max_degree=None, **kwargs):
    """Yield causal relations among a set of distinctions."""
    distinctions = distinctions.unflatten()
    # Self relations
    yield from _self_relations(distinctions)
    # Non-self relations
    combinations = _combinations_with_nonempty_congruent_overlap(
        distinctions, min_degree=min_degree, max_degree=max_degree
    )
    # TODO(refactor) make into pattern
    parallel_kwargs = {
        "parallel": config.PARALLEL_RELATION_EVALUATION,
        "progress": config.PROGRESS_BARS,
        "chunksize": DEFAULT_RELATION_CHUNKSIZE,
        "sequential_threshold": DEFAULT_RELATION_SEQUENTIAL_THRESHOLD,
        "desc": "Evaluating relations",
    }
    parallel_kwargs.update(
        {kwarg: value for kwarg, value in kwargs.items() if kwarg in parallel_kwargs}
    )

    def worker(combination):
        return Relation((distinctions[i] for i in combination))

    yield from MapReduce(
        worker,
        combinations,
        # TODO(relations): use analytical solution to show total?
        **parallel_kwargs,
    ).run()


def _self_relations(distinctions):
    return filter(None, (Relation([distinction]) for distinction in distinctions))


def _combinations_with_nonempty_congruent_overlap(
    components, min_degree=2, max_degree=None
):
    """Return combinations of distinctions with nonempty congruent overlap.

    Arguments:
        components (CauseEffectStructure | FlatCauseEffectStructure): The distinctions or MICE to find overlaps among.
    """
    # TODO(4.0) remove mapping when/if distinctions allow O(1) random access
    mapping = {component: i for i, component in enumerate(components)}
    # Use integers to avoid expensive distinction hashing
    sets = [
        list(map(mapping.get, subset))
        for _, subset in components.purview_inclusion(max_order=1)
    ]
    setset.set_universe(range(len(components)))
    return combinatorics.union_powerset_family(
        sets, min_size=min_degree, max_size=max_degree
    )


class Relations:
    """A set of relations among distinctions."""

    def __init__(self, *args, **kwargs):
        self._num_relations_cached = None
        self._sum_phi_cached = None

    def sum_phi(self):
        if self._sum_phi_cached is None:
            self._sum_phi_cached = self._sum_phi()
        return self._sum_phi_cached

    def num_relations(self):
        if self._num_relations_cached is None:
            self._num_relations_cached = self._num_relations()
        return self._num_relations_cached

    def _repr_columns(self):
        return [
            (f"Σ{fmt.SMALL_PHI}_r", self.sum_phi()),
            ("#(relations)", self.num_relations()),
        ]


class ConcreteRelations(frozenset, Relations):
    def _sum_phi(self):
        return sum(relation.phi for relation in self)

    def _num_relations(self):
        return len(self)

    def __repr__(self):
        body = "\n".join(
            fmt.align_columns(self._repr_columns()) + [fmt.margin(r) for r in self]
        )
        return fmt.header("ConcreteRelations", body, fmt.HEADER_BAR_1, fmt.HEADER_BAR_1)


class AnalyticalRelations(Relations):
    def __init__(self, distinctions):
        self.distinctions = distinctions.unflatten()
        super().__init__()

    @cached_property
    def self_relations(self):
        return tuple(_self_relations(self.distinctions))

    def _sum_phi(self):
        sum_phi = 0
        # Sum of phi excluding self-relations
        for _, overlapping_distinctions in self.distinctions.purview_inclusion(
            max_order=1
        ):
            sum_phi += combinatorics.sum_of_minimum_among_subsets(
                [
                    distinction.phi / len(distinction.purview_union)
                    for distinction in overlapping_distinctions
                ]
            )
        # Count self-relations
        sum_phi += sum(relation.phi for relation in self.self_relations)
        return sum_phi

    def _num_relations(self):
        count = 0
        # Compute number of relations excluding self-relations
        for purview, overlapping_distinctions in self.distinctions.purview_inclusion(
            max_order=None
        ):
            inclusion_exclusion_term = (-1) ** (len(purview) - 1)
            overlap_size_term = (
                2 ** len(overlapping_distinctions) - len(overlapping_distinctions) - 1
            )
            count += inclusion_exclusion_term * overlap_size_term
        # Count self-relations
        count += len(self.self_relations)
        return count

    def __len__(self):
        return self.num_relations()

    def __repr__(self):
        body = "\n".join(fmt.align_columns(self._repr_columns()))
        return fmt.box(fmt.header("AnalyticalRelations", body, "", fmt.HEADER_BAR_2))


_CONGRUENCE_WARNING_MSG = (
    "distinctions.resolve_congruence() has not been called; results may "
    "include relations that do not exist after filtering out distinctions "
    "incongruent with the SIA specified state. Consider using "
    "`new_big_phi.phi_structure()` to obtain a consistent structure."
)


def relations(distinctions, relation_computation=None, **kwargs):
    """Return causal relations among a set of distinctions."""
    if not distinctions.resolved_congruence:
        warnings.warn(_CONGRUENCE_WARNING_MSG, PyPhiWarning, stacklevel=2)
    return relation_computations[
        fallback(relation_computation, config.RELATION_COMPUTATION)
    ](distinctions, **kwargs)


class RelationComputationsRegistry(Registry):
    """Storage for functions for computing relations.

    Users can define custom schemes:

    Examples:
        >>> @relation_computations.register('NONE')  # doctest: +SKIP
        ... def no_relations(subsystem, ces):
        ...    return Relations([])

    And use them by setting ``config.RELATION_COMPUTATIONS = 'NONE'``
    """

    desc = "methods for computing relations"


relation_computations = RelationComputationsRegistry()


@relation_computations.register("CONCRETE")
def concrete_relations(distinctions, **kwargs):
    return ConcreteRelations(all_relations(distinctions, **kwargs))


@relation_computations.register("ANALYTICAL")
def analytical_relations(distinctions, **kwargs):
    return AnalyticalRelations(distinctions)


# Functional alias
def relation(distinctions):
    return Relation(distinctions)
