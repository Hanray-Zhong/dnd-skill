from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from dnd_5e.formulas import FormulaCatalog
from dnd_5e.state.formulas import commit_formula_calculation
from dnd_5e.state.types import FormulaCalculationRequest, InvalidStateRequest
from tests.facade_support import run_facade
from tests.test_formula_recalculation import _create_ready_campaign


class FormulaStateBoundaryTests(unittest.TestCase):
    def test_state_boundary_recomputes_before_accepting_a_derived_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            _create_ready_campaign(workspace)
            inputs: dict[str, object] = {
                "ability_score": {"value": 15, "unit": "ability_score"}
            }
            modifiers: list[dict[str, object]] = []
            calculation = FormulaCatalog().calculate(
                formula_id="ability-modifier",
                character_id="aria",
                inputs=inputs,
                modifiers=modifiers,
            )
            tampered = copy.deepcopy(calculation)
            result = tampered["result"]
            assert isinstance(result, dict)
            result["value"] = 99
            request = FormulaCalculationRequest(
                expected_revision=2,
                idempotency_key="tampered-calculation",
                character_id="aria",
                formula_id="ability-modifier",
                inputs=inputs,
                modifiers=modifiers,
                calculation=tampered,
                source="dnd-5e-character",
                audience_id="dm",
            )

            with self.assertRaises(InvalidStateRequest):
                commit_formula_calculation(
                    workspace / "state" / "campaign.sqlite3",
                    request=request,
                    event_id=str(uuid.uuid4()),
                    committed_at="2026-08-23T00:00:00Z",
                )

            opened = run_facade("open", str(workspace))
            payload = json.loads(opened.stdout) if opened.stdout else None
            self.assertEqual(0, opened.returncode, msg=opened.stderr)
            assert isinstance(payload, dict)
            self.assertEqual(2, payload["revision"])
            self.assertNotIn("derived_values", payload)


if __name__ == "__main__":
    unittest.main()
