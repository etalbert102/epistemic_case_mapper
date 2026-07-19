"""Ordered implementation stages for the epistemic case-mapping pipeline.

Stage packages intentionally avoid eager re-exports so importing one stage does
not initialize the dense dependency graph of a later stage.
"""
