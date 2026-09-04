"""Vectorized Monte-Carlo rollout kernels for the pick-recommendation engine.

The batched numpy fast paths that keep a full-depth recommendation under the 10-second
acceptance bar: a greedy-opponent kernel and a deterministic per-manager fitted-opponent
kernel, plus the object-model fallback. All three share one pool/manager/schedule setup
(:func:`_build_rollout_arrays`) and one owner-turn policy (:func:`_owner_step`) so the
greedy and fitted paths cannot silently diverge. See
:mod:`draft_oracle.optimize.recommend` for the engine rationale.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from draft_oracle.optimize._recommend_core import (
    _POS_INDEX,
    _ROLLOUT_SALT,
    RecommendConfig,
    _owner_roster_value,
    _prune_candidates,
    _rollout_owner_value,
    _RolloutInput,
    asset_value,
    replacement_levels,
)
from draft_oracle.optimize._recommend_kernel_utils import (
    _affinity_row,
    _FittedChoiceInputs,
    _GreedyChoiceInputs,
)
from draft_oracle.optimize._recommend_kernel_utils import (
    _fitted_opponent_choice as _fitted_opponent_choice_impl,
)
from draft_oracle.optimize._recommend_kernel_utils import (
    _greedy_opponent_choice as _greedy_opponent_choice_impl,
)
from draft_oracle.optimize.opponents import FittedOpponentModel
from draft_oracle.optimize.simulator import (
    DraftAsset,
    DraftState,
    GreedyOpponentModel,
    OpponentModel,
)


def _require_legal_rows(legal: np.ndarray, manager: str) -> None:
    """Raise if any rollout row has no legal asset for ``manager``.

    The object-model rollout raises ``ValueError`` from ``greedy_vor_pick`` /
    ``OpponentModel.pick`` when a manager has nothing legal to draft. The vectorized
    kernel must fail the same way: an ``argmax`` over an all -inf row silently returns
    index 0 and drafts whatever asset happens to sit there, corrupting the rollout.
    """
    if not bool(legal.any(axis=1).all()):
        raise ValueError(f"manager {manager!r} has no legal asset to draft")


def _vec_fill_owner(
    request: _OwnerFillRequest,
) -> None:
    """Vectorized greedy-VOR fill of the owner's remaining slots (opponents ignored)."""
    rows = np.arange(request.alive.shape[0])
    neg_inf = float("-inf")
    for _ in range(request.remaining):
        cap_ok = request.counts[:, request.owner_idx, :] < request.limits
        legal = request.alive & cap_ok[:, request.posc]
        has_legal = legal.any(axis=1)
        if not has_legal.any():
            break
        scores = np.where(legal, request.vor_owner[None, :], neg_inf)
        choice = np.argmax(scores, axis=1)
        # Match the object path's ``_fill_owner_greedily``: a row with no legal asset
        # simply stops filling (the owner gets fewer picks) rather than the argmax
        # over all -inf silently drafting pool index 0.
        active = rows[has_legal]
        chosen = choice[has_legal]
        request.owner_total[active] += request.val[chosen]
        request.alive[active, chosen] = False
        request.counts[active, request.owner_idx, request.posc[chosen]] += 1


@dataclass(frozen=True)
class _OwnerFillRequest:
    alive: np.ndarray
    counts: np.ndarray
    owner_idx: int
    val: np.ndarray
    vor_owner: np.ndarray
    posc: np.ndarray
    limits: np.ndarray
    owner_total: np.ndarray
    remaining: int


@dataclass(frozen=True)
class _RolloutArrays:
    """Numpy views of a draft state shared by every vectorized rollout kernel.

    Depends only on ``(state, owner, replacement)`` — never on the candidate or the
    opponent model — so the greedy, fitted, and owner-fill paths all read one identical
    board layout and cannot drift apart.
    """

    pool: list[DraftAsset]
    n_assets: int
    key_to_idx: dict[str, int]
    val: np.ndarray
    rank_val: np.ndarray
    key_order: np.ndarray
    posc: np.ndarray
    vor_owner: np.ndarray
    mgr_ids: list[str]
    mid_to_idx: dict[str, int]
    n_managers: int
    limits: np.ndarray
    base_counts: np.ndarray
    owner_idx: int
    cap_total: int
    rem_m: list[int]
    last_owner_k: int
    base_owner_value: float


@dataclass(frozen=True)
class _AssetArrays:
    pool: list[DraftAsset]
    n_assets: int
    key_to_idx: dict[str, int]
    val: np.ndarray
    rank_val: np.ndarray
    key_order: np.ndarray
    posc: np.ndarray
    vor_owner: np.ndarray


@dataclass(frozen=True)
class _ManagerArrays:
    mgr_ids: list[str]
    mid_to_idx: dict[str, int]
    n_managers: int
    limits: np.ndarray
    base_counts: np.ndarray
    owner_idx: int
    cap_total: int
    rem_m: list[int]
    last_owner_k: int


def _build_rollout_arrays(
    state: DraftState, owner: str, replacement: Mapping[str, float]
) -> _RolloutArrays:
    """Build the pool/manager/schedule numpy arrays shared by the rollout kernels."""
    asset_arrays = _build_asset_arrays(state, replacement)
    manager_arrays = _build_manager_arrays(state, owner)

    return _RolloutArrays(
        pool=asset_arrays.pool,
        n_assets=asset_arrays.n_assets,
        key_to_idx=asset_arrays.key_to_idx,
        val=asset_arrays.val,
        rank_val=asset_arrays.rank_val,
        key_order=asset_arrays.key_order,
        posc=asset_arrays.posc,
        vor_owner=asset_arrays.vor_owner,
        mgr_ids=manager_arrays.mgr_ids,
        mid_to_idx=manager_arrays.mid_to_idx,
        n_managers=manager_arrays.n_managers,
        limits=manager_arrays.limits,
        base_counts=manager_arrays.base_counts,
        owner_idx=manager_arrays.owner_idx,
        cap_total=manager_arrays.cap_total,
        rem_m=manager_arrays.rem_m,
        last_owner_k=manager_arrays.last_owner_k,
        base_owner_value=_owner_roster_value(state, owner),
    )


def _build_asset_arrays(
    state: DraftState,
    replacement: Mapping[str, float],
) -> _AssetArrays:
    pool = sorted(state.available.values(), key=lambda asset: (-asset_value(asset), asset.key))
    n_assets = len(pool)
    val = np.array([asset_value(asset) for asset in pool], dtype="float64")
    posc = np.array([_POS_INDEX[asset.position] for asset in pool], dtype="int64")
    return _AssetArrays(
        pool=pool,
        n_assets=n_assets,
        key_to_idx={asset.key: i for i, asset in enumerate(pool)},
        val=val,
        rank_val=np.array([asset.rank_value for asset in pool], dtype="float64"),
        key_order=_key_order(pool, n_assets),
        posc=posc,
        vor_owner=val - _replacement_array(replacement)[posc],
    )


def _replacement_array(replacement: Mapping[str, float]) -> np.ndarray:
    return np.array([replacement["F"], replacement["D"], replacement["G"]], dtype="float64")


def _key_order(pool: Sequence[DraftAsset], n_assets: int) -> np.ndarray:
    key_order = np.empty(n_assets, dtype="int64")
    key_order[np.argsort([asset.key for asset in pool])] = np.arange(n_assets)
    return key_order


def _build_manager_arrays(state: DraftState, owner: str) -> _ManagerArrays:
    mgr_ids = list(dict.fromkeys(state.order))
    mid_to_idx = {manager: i for i, manager in enumerate(mgr_ids)}
    limits = _capacity_limits(state)
    base_counts = _base_counts(state, mid_to_idx, len(mgr_ids))
    owner_idx = mid_to_idx[owner]
    cap_total = state.capacity.total
    rem_m = [mid_to_idx[manager] for manager in state.order[state.pick_index :]]
    last_owner_k = _last_owner_pick_index(rem_m, owner_idx, cap_total, base_counts)
    return _ManagerArrays(
        mgr_ids=mgr_ids,
        mid_to_idx=mid_to_idx,
        n_managers=len(mgr_ids),
        limits=limits,
        base_counts=base_counts,
        owner_idx=owner_idx,
        cap_total=cap_total,
        rem_m=rem_m,
        last_owner_k=last_owner_k,
    )


def _capacity_limits(state: DraftState) -> np.ndarray:
    cap = state.capacity
    return np.array([cap.forwards, cap.defense, cap.goalies], dtype="int64")


def _base_counts(
    state: DraftState,
    mid_to_idx: Mapping[str, int],
    n_managers: int,
) -> np.ndarray:
    base_counts = np.zeros((n_managers, 3), dtype="int64")
    for manager, roster in state.rosters.items():
        base_counts[mid_to_idx[manager]] = [
            roster.count("F"),
            roster.count("D"),
            roster.count("G"),
        ]
    return base_counts


def _last_owner_pick_index(
    rem_m: Sequence[int],
    owner_idx: int,
    cap_total: int,
    base_counts: np.ndarray,
) -> int:
    owner_needed = cap_total - int(base_counts[owner_idx].sum())
    owner_positions = [index for index, manager_idx in enumerate(rem_m) if manager_idx == owner_idx]
    return owner_positions[owner_needed - 1]


def _init_candidate_rollout(
    arr: _RolloutArrays, asset: DraftAsset, rollouts: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Seed the per-candidate rollout batch with the owner having taken ``asset`` now."""
    idx_c = arr.key_to_idx[asset.key]
    alive = np.ones((rollouts, arr.n_assets), dtype=bool)
    counts = np.broadcast_to(arr.base_counts, (rollouts, arr.n_managers, 3)).copy()
    owner_total = np.zeros(rollouts, dtype="float64")
    alive[:, idx_c] = False
    counts[:, arr.owner_idx, arr.posc[idx_c]] += 1
    owner_total += arr.val[idx_c]
    return alive, counts, owner_total, 1


@dataclass
class _OwnerStep:
    """Outcome of the owner's turn inside a vectorized rollout batch."""

    done: bool
    choice: np.ndarray | None
    owner_total: np.ndarray
    owner_taken: int


@dataclass
class _CandidateRollout:
    alive: np.ndarray
    counts: np.ndarray
    owner_total: np.ndarray
    owner_taken: int


@dataclass(frozen=True)
class _OwnerStepRequest:
    arr: _RolloutArrays
    cfg: RecommendConfig
    batch: _CandidateRollout
    legal: np.ndarray


def _owner_step(
    request: _OwnerStepRequest,
) -> _OwnerStep:
    """Advance the owner's greedy-VOR turn (or fill the tail once ``depth`` is hit).

    Identical to the object path's owner behaviour: past ``depth`` the remaining slots
    are filled greedily from the current pool and the rollout is done; otherwise the
    owner takes the best legal VOR asset.
    """
    if request.cfg.depth is not None and request.batch.owner_taken >= request.cfg.depth:
        _vec_fill_owner(
            _OwnerFillRequest(
                request.batch.alive,
                request.batch.counts,
                request.arr.owner_idx,
                request.arr.val,
                request.arr.vor_owner,
                request.arr.posc,
                request.arr.limits,
                request.batch.owner_total,
                request.arr.cap_total - request.batch.owner_taken,
            )
        )
        return _OwnerStep(True, None, request.batch.owner_total, request.arr.cap_total)
    _require_legal_rows(request.legal, request.arr.mgr_ids[request.arr.owner_idx])
    scores = np.where(request.legal, request.arr.vor_owner[None, :], float("-inf"))
    choice = np.argmax(scores, axis=1)
    owner_total = request.batch.owner_total + request.arr.val[choice]
    return _OwnerStep(False, choice, owner_total, request.batch.owner_taken + 1)


@dataclass(frozen=True)
class _Turn:
    """One manager's per-rollout position counts + legality mask for the current pick."""

    cnt_m: np.ndarray
    legal: np.ndarray


def _greedy_opponent_choice(
    arr: _RolloutArrays,
    gmodel: GreedyOpponentModel,
    turn: _Turn,
    rng: np.random.Generator,
) -> np.ndarray:
    return _greedy_opponent_choice_impl(
        _GreedyChoiceInputs(
            arr.rank_val,
            arr.limits,
            arr.posc,
            arr.key_order,
            gmodel.need_weight,
            gmodel.temperature,
            turn.cnt_m,
            turn.legal,
            rng,
        )
    )


def _fitted_opponent_choice(
    arr: _RolloutArrays,
    params: _FittedParams,
    turn: _Turn,
    mgr_i: int,
) -> np.ndarray:
    return _fitted_opponent_choice_impl(
        _FittedChoiceInputs(
            arr.rank_val,
            arr.limits,
            arr.posc,
            arr.key_order,
            params.coef_rank,
            params.coef_aff,
            params.aff_matrix,
            params.need_weight,
            turn.cnt_m,
            turn.legal,
            mgr_i,
        )
    )


def _vectorized_greedy_expected(
    state: DraftState | _GreedyExpectedRequest,
    *legacy: object,
) -> list[float]:
    """Batched Monte-Carlo expected owner value against a greedy opponent (US-021).

    The pick order is identical across rollouts, so the whole 500-rollout batch is
    advanced in lockstep as numpy arrays: only the opponents' softmax draws differ per
    rollout. This is the "vectorized rollouts" the acceptance calls for and keeps a
    full-depth 12-manager recommendation well under the 10-second bar. Semantics match
    the object-model rollout (greedy-VOR owner tail, opponent ``rank_value + need``
    softmax, owner-full early stop, ``depth`` cap).
    """
    request = _resolve_greedy_expected_request(state, *legacy)
    arr = _build_rollout_arrays(request.state, request.owner, request.replacement)
    return _candidate_expected_means(
        request.candidate_assets,
        arr.base_owner_value,
        lambda asset: _greedy_owner_total(arr, request, asset),
    )


@dataclass(frozen=True)
class _GreedyExpectedRequest:
    state: DraftState
    owner: str
    candidate_assets: Sequence[DraftAsset]
    gmodel: GreedyOpponentModel
    replacement: Mapping[str, float]
    cfg: RecommendConfig


@dataclass(frozen=True)
class _AdvanceRolloutRequest:
    arr: _RolloutArrays
    cfg: RecommendConfig
    batch: _CandidateRollout
    choose_opponent: Callable[[_Turn, int], np.ndarray]


@dataclass(frozen=True)
class _FittedExpectedRequest:
    state: DraftState
    owner: str
    candidate_assets: Sequence[DraftAsset]
    models: Mapping[str, FittedOpponentModel]
    replacement: Mapping[str, float]
    cfg: RecommendConfig


@dataclass(frozen=True)
class _ExpectedValueRequest:
    state: DraftState
    owner: str
    asset: DraftAsset
    opponent_model: OpponentModel | Mapping[str, OpponentModel]
    replacement: Mapping[str, float]
    cfg: RecommendConfig


@dataclass(frozen=True)
class _LegacyExpectedArgs:
    owner: str
    candidate_assets: Sequence[DraftAsset]
    model_like: object
    replacement: Mapping[str, float]
    cfg: RecommendConfig


def _resolve_greedy_expected_request(
    state: DraftState | _GreedyExpectedRequest,
    *legacy: object,
) -> _GreedyExpectedRequest:
    if isinstance(state, _GreedyExpectedRequest):
        return state
    request = _legacy_expected_args(legacy)
    if request is None or not isinstance(request.model_like, GreedyOpponentModel):
        raise TypeError(_LEGACY_GREEDY_EXPECTED_ERROR)
    return _GreedyExpectedRequest(
        state,
        request.owner,
        request.candidate_assets,
        request.model_like,
        request.replacement,
        request.cfg,
    )


def _candidate_rollout(
    arr: _RolloutArrays,
    asset: DraftAsset,
    rollouts: int,
) -> _CandidateRollout:
    alive, counts, owner_total, owner_taken = _init_candidate_rollout(arr, asset, rollouts)
    return _CandidateRollout(alive, counts, owner_total, owner_taken)


def _advance_rollout(request: _AdvanceRolloutRequest) -> None:
    rows = np.arange(request.batch.alive.shape[0])
    for k in range(1, request.arr.last_owner_k + 1):
        manager_idx = request.arr.rem_m[k]
        turn = _turn_state(request.arr, request.batch, manager_idx)
        if manager_idx == request.arr.owner_idx:
            choice = _owner_rollout_choice(
                request.arr,
                request.cfg,
                request.batch,
                turn.legal,
            )
            if choice is None:
                break
        else:
            _require_legal_rows(turn.legal, request.arr.mgr_ids[manager_idx])
            choice = request.choose_opponent(turn, manager_idx)
        request.batch.alive[rows, choice] = False
        request.batch.counts[rows, manager_idx, request.arr.posc[choice]] += 1


def _greedy_owner_total(
    arr: _RolloutArrays,
    request: _GreedyExpectedRequest,
    asset: DraftAsset,
) -> np.ndarray:
    # Common random numbers: identical opponent draws across candidates (pairs the
    # comparison; the seed does not depend on the candidate).
    rng = np.random.default_rng(request.cfg.seed * _ROLLOUT_SALT)
    batch = _candidate_rollout(arr, asset, request.cfg.rollouts)
    _advance_rollout(
        _AdvanceRolloutRequest(
            arr,
            request.cfg,
            batch,
            lambda turn, _manager_idx: _greedy_opponent_choice(
                arr,
                request.gmodel,
                turn,
                rng,
            ),
        )
    )
    return batch.owner_total


def _turn_state(
    arr: _RolloutArrays,
    batch: _CandidateRollout,
    manager_idx: int,
) -> _Turn:
    cnt_m = batch.counts[:, manager_idx, :]
    legal = batch.alive & (cnt_m < arr.limits)[:, arr.posc]
    return _Turn(cnt_m, legal)


def _owner_rollout_choice(
    arr: _RolloutArrays,
    cfg: RecommendConfig,
    batch: _CandidateRollout,
    legal: np.ndarray,
) -> np.ndarray | None:
    step = _owner_step(_OwnerStepRequest(arr, cfg, batch, legal))
    batch.owner_total = step.owner_total
    batch.owner_taken = step.owner_taken
    return step.choice


def _mean_owner_value(owner_total: np.ndarray, base_owner_value: float) -> float:
    # ``owner_total`` accumulates only picks made during this rollout; add the
    # owner's already-drafted roster so E[roster] matches the object path's
    # ``_owner_roster_value`` (one documented definition).
    return float(owner_total.mean()) + base_owner_value


def _fitted_zero_temp_models(
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    state: DraftState,
) -> dict[str, FittedOpponentModel] | None:
    """The per-manager fitted models iff every opponent seat maps to a temperature-0 one.

    Guards the vectorized fitted fast path: it can only reproduce a deterministic
    (argmax) fitted policy, so a positive-temperature (sampling) model, a mixed set,
    or a missing seat forces the general object-model rollout instead.
    """
    if not isinstance(opponent_model, Mapping):
        return None
    models: dict[str, FittedOpponentModel] = {}
    for manager in dict.fromkeys(state.order):
        model = opponent_model.get(manager)
        if not isinstance(model, FittedOpponentModel) or model.temperature > 0.0:
            return None
        models[manager] = model
    return models


@dataclass(frozen=True)
class _FittedParams:
    """Per-manager fitted utility coefficients indexed by manager row."""

    coef_rank: np.ndarray
    coef_aff: np.ndarray
    aff_matrix: np.ndarray
    need_weight: np.ndarray


def _build_fitted_params(
    models: Mapping[str, FittedOpponentModel], arr: _RolloutArrays
) -> _FittedParams:
    """Assemble each fitted opponent's rank/affinity/need parameters as numpy arrays."""
    coef_rank = np.zeros(arr.n_managers, dtype="float64")
    coef_aff = np.zeros(arr.n_managers, dtype="float64")
    aff_matrix = np.zeros((arr.n_managers, arr.n_assets), dtype="float64")
    need_weight = np.zeros(arr.n_managers, dtype="float64")
    for manager, model in models.items():
        idx = arr.mid_to_idx[manager]
        coef_rank[idx] = model.coefficients.rank
        coef_aff[idx] = model.coefficients.affinity
        need_weight[idx] = model.need_weight
        aff_matrix[idx] = _affinity_row(arr.pool, model.affinity)
    return _FittedParams(coef_rank, coef_aff, aff_matrix, need_weight)


def _vectorized_fitted_expected(
    state: DraftState | _FittedExpectedRequest,
    *legacy: object,
) -> list[float]:
    """Batched expected owner value against deterministic per-manager fitted opponents.

    The fitted analogue of :func:`_vectorized_greedy_expected`: the owner still fills
    via greedy-VOR (:func:`_owner_step`), but each opponent seat scores legal assets by
    its own ``beta_rank * rank_z + beta_affinity * affinity + need_weight * need``
    utility (``rank_z`` standardized within the legal set per base position, exactly as
    :meth:`FittedOpponentModel._utilities`), advanced across the whole rollout batch in
    lockstep. This keeps the fitted recommend under the 10s budget at ``rollouts>=500``
    without falling back to the per-pick Python object rollout.
    """
    request = _resolve_fitted_expected_request(state, legacy)
    arr = _build_rollout_arrays(request.state, request.owner, request.replacement)
    params = _build_fitted_params(request.models, arr)
    return _candidate_expected_means(
        request.candidate_assets,
        arr.base_owner_value,
        lambda asset: _fitted_owner_total(arr, params, request, asset),
    )


def _resolve_fitted_expected_request(
    state: DraftState | _FittedExpectedRequest,
    legacy: tuple[object, ...],
) -> _FittedExpectedRequest:
    if isinstance(state, _FittedExpectedRequest):
        return state
    request = _legacy_expected_args(legacy)
    if request is None or not isinstance(request.model_like, Mapping):
        raise TypeError(_LEGACY_FITTED_EXPECTED_ERROR)
    return _FittedExpectedRequest(
        state,
        request.owner,
        request.candidate_assets,
        request.model_like,
        request.replacement,
        request.cfg,
    )


_LEGACY_GREEDY_EXPECTED_ERROR = (
    "legacy greedy expected calls require owner, candidates, model, replacement, and config"
)
_LEGACY_FITTED_EXPECTED_ERROR = (
    "legacy fitted expected calls require owner, candidates, models, replacement, and config"
)


def _legacy_expected_args(
    legacy: tuple[object, ...],
) -> _LegacyExpectedArgs | None:
    if len(legacy) != 5:
        return None
    owner, candidate_assets, model_like, replacement, cfg = legacy
    if not isinstance(owner, str):
        return None
    if not isinstance(candidate_assets, Sequence):
        return None
    if not isinstance(replacement, Mapping):
        return None
    if not isinstance(cfg, RecommendConfig):
        return None
    return _LegacyExpectedArgs(owner, candidate_assets, model_like, replacement, cfg)


def _fitted_owner_total(
    arr: _RolloutArrays,
    params: _FittedParams,
    request: _FittedExpectedRequest,
    asset: DraftAsset,
) -> np.ndarray:
    batch = _candidate_rollout(arr, asset, request.cfg.rollouts)
    _advance_rollout(
        _AdvanceRolloutRequest(
            arr,
            request.cfg,
            batch,
            lambda turn, manager_idx: _fitted_opponent_choice(
                arr,
                params,
                turn,
                manager_idx,
            ),
        )
    )
    return batch.owner_total


def _candidate_expected_means(
    candidate_assets: Sequence[DraftAsset],
    base_owner_value: float,
    owner_total_for_asset: Callable[[DraftAsset], np.ndarray],
) -> list[float]:
    return [
        _mean_owner_value(owner_total_for_asset(asset), base_owner_value)
        for asset in candidate_assets
    ]


def _expected_value(
    request: DraftState | _ExpectedValueRequest,
    *legacy: object,
) -> float:
    """Mean final owner-roster value if ``asset`` is taken now (seeded rollouts).

    Rollout ``j`` is seeded from ``j`` alone (not the candidate), so every candidate
    faces the *same* opponent draws per rollout — common random numbers, which pairs
    the candidate comparison and slashes the variance of their differences so a modest
    rollout count still ranks picks correctly.
    """
    resolved = _resolve_expected_value_request(request, *legacy)
    total = 0.0
    query = _RolloutInput(
        resolved.state,
        resolved.owner,
        resolved.asset,
        resolved.opponent_model,
        resolved.replacement,
        resolved.cfg.depth,
    )
    for rollout in range(resolved.cfg.rollouts):
        rng = random.Random(resolved.cfg.seed * _ROLLOUT_SALT + rollout)
        total += _rollout_owner_value(query, rng)
    return total / resolved.cfg.rollouts


def _resolve_expected_value_request(
    request: DraftState | _ExpectedValueRequest,
    *legacy: object,
) -> _ExpectedValueRequest:
    if isinstance(request, _ExpectedValueRequest):
        return request
    if len(legacy) != 5:
        raise TypeError(
            "legacy expected value calls require owner, asset/model, replacement, and config"
        )
    owner, asset, opponent_model, replacement, cfg = legacy
    if not isinstance(owner, str):
        raise TypeError("legacy expected value calls require string owner")
    if not isinstance(asset, DraftAsset):
        raise TypeError(
            "legacy expected value calls require DraftAsset as third positional argument"
        )
    if not isinstance(opponent_model, (OpponentModel, Mapping)):
        raise TypeError("legacy expected value calls require opponent model or mapping")
    if not isinstance(replacement, Mapping):
        raise TypeError("legacy expected value calls require replacement mapping")
    if not isinstance(cfg, RecommendConfig):
        raise TypeError("legacy expected value calls require RecommendConfig")
    return _ExpectedValueRequest(
        request,
        owner,
        asset,
        opponent_model,
        replacement,
        cfg,
    )


def _expected_values(
    state: DraftState,
    owner: str,
    candidate_assets: Sequence[DraftAsset],
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    replacement: Mapping[str, float],
    cfg: RecommendConfig,
) -> list[float]:
    """Expected final owner value per candidate, vectorized where possible.

    Uses the batched numpy kernel when the opponents are a single greedy model or a
    per-manager set of deterministic fitted models (the <10s fast paths); otherwise
    falls back to the general object-model rollout.
    """
    if isinstance(opponent_model, GreedyOpponentModel):
        return _vectorized_greedy_expected(
            _GreedyExpectedRequest(
                state,
                owner,
                candidate_assets,
                opponent_model,
                replacement,
                cfg,
            )
        )
    fitted_models = _fitted_zero_temp_models(opponent_model, state)
    if fitted_models is not None:
        return _vectorized_fitted_expected(
            _FittedExpectedRequest(
                state,
                owner,
                candidate_assets,
                fitted_models,
                replacement,
                cfg,
            )
        )
    return [
        _expected_value(
            _ExpectedValueRequest(
                state,
                owner,
                asset,
                opponent_model,
                replacement,
                cfg,
            )
        )
        for asset in candidate_assets
    ]


def choose_pick(
    state: DraftState,
    owner: str,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    *,
    config: RecommendConfig | None = None,
    managers: int | None = None,
) -> DraftAsset:
    """Lean argmax pick: rollout-expected best asset, skipping explanations/survival.

    The policy used by the strategy comparison and any caller that only needs the
    chosen asset. Same rollout as ``recommend_pick`` but without the survival estimate
    or the explained board, so it is cheap enough to call at every pick of a full
    simulated draft.
    """
    cfg = config or RecommendConfig()
    n_managers = managers if managers is not None else len(state.rosters)
    replacement = replacement_levels(state, n_managers)
    candidates = _prune_candidates(state, owner, replacement, cfg.max_candidates)
    if not candidates:
        raise ValueError(f"owner {owner!r} has no legal pick")
    expecteds = _expected_values(
        state, owner, [c.asset for c in candidates], opponent_model, replacement, cfg
    )
    # argmax by expected, then VOR, then key ascending — the object-model tie-break,
    # expressed as one deterministic sort so there is no compound branch.
    ranked = sorted(
        zip(candidates, expecteds, strict=True),
        key=lambda pair: (-pair[1], -pair[0].vor, pair[0].asset.key),
    )
    return ranked[0][0].asset
