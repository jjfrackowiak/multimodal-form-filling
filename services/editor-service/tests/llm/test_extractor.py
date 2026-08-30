from __future__ import annotations

from editor_service.llm.extractor import VertexJsonExtractor, _extract_json_object


def test_extract_json_object_strips_fence() -> None:
    raw = '```json\n{"requirements": []}\n```'
    assert _extract_json_object(raw) == {"requirements": []}


def test_to_requirement_projects_constraint() -> None:
    req = VertexJsonExtractor._to_requirement(
        {
            "text": "Two headliner photographs.",
            "source_span": "2x headliner",
            "expected_count": 2,
            "constraint": {
                "kind": "camera_position",
                "value": "between_front_seats",
                "source_span": "between the seats",
            },
        }
    )
    assert req.text.startswith("Two headliner")
    assert req.expected_count == 2
    assert req.constraint is not None
    assert req.constraint.value == "between_front_seats"
