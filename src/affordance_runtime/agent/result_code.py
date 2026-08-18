"""Stable Runtime failure codes independent of public result projection."""

from enum import StrEnum


class AgentFailureCode(StrEnum):
    NO_PROGRESS_REPETITION = "no_progress_repetition"
    NO_PROGRESS_CONTROL_REPETITION = "no_progress_control_repetition"
    REPEATED_FAILURE_LIMIT = "repeated_failure_limit"
    OBSERVATION_CAPABILITY_UNAVAILABLE = "observation_capability_unavailable"
    OBSERVATION_ACQUISITION_FAILED = "observation_acquisition_failed"
    OBSERVATION_FRESHNESS_INVALID = "observation_freshness_invalid"
    OBSERVATION_ORIGIN_INVALID = "observation_origin_invalid"
    POST_ACTION_CAPABILITY_UNAVAILABLE = "post_action_capability_unavailable"
    POST_ACTION_ACQUISITION_FAILED = "post_action_acquisition_failed"
    POST_ACTION_FRESHNESS_INVALID = "post_action_freshness_invalid"
    POST_ACTION_ORIGIN_INVALID = "post_action_origin_invalid"
