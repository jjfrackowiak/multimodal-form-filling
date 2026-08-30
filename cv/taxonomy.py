"""Prompt text for the inventory labeler. The schema is `schema.ImageLabel`."""

LABEL_TASK = """
Label this vehicle-return inspection photo.

Fill the structured fields. Put facts a Word comment would cite in the typed
fields (odometer_km, warnings, registration, pose_evidence, seat_side,
diagonal), not only in note.

shot_from is required only when depicts is headliner.
"""
