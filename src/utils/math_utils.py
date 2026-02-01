from decimal import Decimal
from itertools import combinations
from typing import List, Tuple, Optional


def find_subset_match(
    target_amounts: List[Decimal],
    pool_amounts: List[Decimal],
    tolerance: Decimal = Decimal("0.05"),
) -> Optional[Tuple[List[int], List[int]]]:
    """
    Finds a subset of target_amounts and a subset of pool_amounts that sum up to the same value
    (within tolerance).

    Returns:
        (indices_of_target, indices_of_pool) OR None if no match found.

    Complexity: O(2^N + 2^M). Keep inputs small (< 15 items recommended).
    """
    # 1. Generate all subset sums for targets
    target_sums = {}  # sum -> [indices]
    n_targets = len(target_amounts)

    # Optimization: limit combination size to prevent explosion
    max_k = min(n_targets, 6)

    for r in range(1, max_k + 1):
        for indices in combinations(range(n_targets), r):
            s = sum(target_amounts[i] for i in indices)
            # Store the first combination that sums to s (simplified)
            if s not in target_sums:
                target_sums[s] = indices

    # 2. Generate all subset sums for pool and check against targets
    n_pool = len(pool_amounts)
    max_j = min(n_pool, 6)

    for r in range(1, max_j + 1):
        for indices in combinations(range(n_pool), r):
            s = sum(pool_amounts[i] for i in indices)

            if s in target_sums:
                return (list(target_sums[s]), list(indices))

            for t_sum, t_indices in target_sums.items():
                if abs(t_sum - s) <= tolerance:
                    return (list(t_indices), list(indices))

    return None
