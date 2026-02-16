from pathlib import Path

from attractor.artifacts import ArtifactStore
from attractor.context import Context
from attractor.engine import ExecutionEngine, ExecutionResult
from attractor.handlers import create_default_registry
from attractor.parser.parser import parse_dot
from attractor.stylesheet import parse_stylesheet
from attractor.transforms import apply_stylesheet
from attractor.validation import validate_graph


def run(
    dot_source: str,
    stylesheet_source: str | None = None,
    context: Context | None = None,
    artifact_dir: str | Path | None = None,
) -> ExecutionResult:
    graph = parse_dot(dot_source)

    if stylesheet_source:
        stylesheet = parse_stylesheet(stylesheet_source)
        graph = apply_stylesheet(graph, stylesheet)

    validation = validate_graph(graph)
    if validation.errors:
        raise ValueError("Invalid graph: " + "; ".join(validation.errors))

    runtime_context = context or Context({})
    engine = ExecutionEngine(handler_registry=create_default_registry())
    result = engine.execute(graph, runtime_context)

    if artifact_dir is not None:
        store = ArtifactStore(artifact_dir)
        store.write_text("run.json", str({"visited_nodes": result.visited_nodes}))

    return result
