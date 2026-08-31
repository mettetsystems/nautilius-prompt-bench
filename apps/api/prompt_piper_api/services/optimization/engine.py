from __future__ import annotations

from prompt_piper_api.domain.optimization import OptimizationResult
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.optimization.binding_preservation_pass import BindingPreservationPass
from prompt_piper_api.services.optimization.constraint_graph_pass import ConstraintGraphPass
from prompt_piper_api.services.optimization.deconfliction_pass import DeconflictionPass
from prompt_piper_api.services.optimization.denoising_pass import DenoisingPass
from prompt_piper_api.services.optimization.metrics import ApprovalExportPass
from prompt_piper_api.services.optimization.rewrite_pass import RewriteCompressionPass
from prompt_piper_api.services.requirement_capture import collect_optimization_binding_phrases


class TokenOptimizationEngine:
    """Five-pass local optimizer: expand for clarity, then denoise and deconflict."""

    def __init__(self) -> None:
        self._graph_pass = ConstraintGraphPass()
        self._rewrite_pass = RewriteCompressionPass()
        self._denoise_pass = DenoisingPass()
        self._deconflict_pass = DeconflictionPass()
        self._binding_pass = BindingPreservationPass()
        self._approval_pass = ApprovalExportPass()

    def optimize(self, body: str, card: RequirementCard) -> OptimizationResult:
        graph = self._graph_pass.run(body, card)
        protected_phrases = collect_optimization_binding_phrases(graph, card)

        rewritten, compressed = self._rewrite_pass.run(body, card, graph)
        denoised, removed = self._denoise_pass.run(rewritten, protected_phrases=protected_phrases)

        body_conflicts = DeconflictionPass.detect_in_body(denoised)
        for conflict in body_conflicts:
            if conflict.description not in {item.description for item in graph.contradictions}:
                graph.contradictions.append(conflict)

        deconflicted, hard_conflicts, resolved = self._deconflict_pass.run(denoised, graph)
        preserved_body, preserved = self._binding_pass.run(deconflicted, graph, card)
        if preserved:
            compressed = [*compressed, *preserved]

        return self._approval_pass.run(
            original_body=body,
            optimized_body=preserved_body,
            graph=graph,
            card=card,
            removed=removed,
            compressed=compressed,
            conflicts_resolved=resolved,
            hard_conflicts=hard_conflicts,
        )

    def approve(self, result: OptimizationResult) -> OptimizationResult:
        if result.hard_conflicts:
            return result.model_copy(update={"export_ready": False, "approved": False})
        return result.model_copy(update={"export_ready": True, "approved": True})
