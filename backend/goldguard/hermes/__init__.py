"""Narrow, proposal-only bridge to the isolated Hermes research agent."""

from goldguard.hermes.client import HermesClient, HermesUnavailable
from goldguard.hermes.generator import (
    ProposalValidationError,
    StrategyProposalGenerator,
)
from goldguard.hermes.models import StrategyProposal
from goldguard.hermes.service import ProposalService

__all__ = [
    "HermesClient",
    "HermesUnavailable",
    "ProposalService",
    "ProposalValidationError",
    "StrategyProposal",
    "StrategyProposalGenerator",
]
