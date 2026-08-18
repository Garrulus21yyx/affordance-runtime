from affordance_runtime.actions.capabilities import VerificationFamily, verification_contract_for_action


def verification_kwargs(
    semantic_action: str,
    schema_digest: str,
    semantic_effects: tuple[str, ...] = (),
    observation_barrier: bool = True,
    *,
    family: VerificationFamily | None = None,
) -> dict[str, str]:
    contract = verification_contract_for_action(
        semantic_action,
        schema_digest,
        semantic_effects,
        observation_barrier,
        family=family,
    )
    return {
        "verification_family": contract.family.value,
        "verification_contract_digest": contract.digest,
    }
