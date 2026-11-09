from pathlib import Path

import pytest

from src.inputs.chef.analyzer import ChefSubagent
from src.inputs.chef.execution_tree_builder import ExecutionTreeBuilder
from src.inputs.chef.models import (
    ConditionalExecution,
    DataBagExecution,
    DataBagItemAnalysis,
    RecipeAnalysisResult,
    RecipeExecutionAnalysis,
    ResourceExecution,
    StructuredAnalysis,
)
from src.inputs.chef.path_resolver import ChefPathResolver
from src.utils.logging import get_logger


def test_collects_plain_and_encrypted_data_bag_items(tmp_path: Path) -> None:
    bag_dir = tmp_path / "data_bags" / "applications"
    bag_dir.mkdir(parents=True)
    (bag_dir / "public.json").write_text(
        '{"id": "public", "document_root": "/opt/public"}'
    )
    (bag_dir / "secret.json").write_text(
        """{
          "id": "secret",
          "token": {
            "encrypted_data": "ciphertext",
            "iv": "initializer-vector",
            "version": 1,
            "cipher": "aes-256-cbc"
          }
        }"""
    )

    items = ChefSubagent._collect_data_bags([tmp_path], lambda *_: None)

    assert [(item.data_bag, item.item_id) for item in items] == [
        ("applications", "public"),
        ("applications", "secret"),
    ]
    assert items[0].data == {"id": "public", "document_root": "/opt/public"}
    assert items[1].encrypted is True
    assert items[1].data == {}
    assert items[1].keys == ["id", "token"]


@pytest.mark.parametrize(
    ("metadata_name", "metadata_content"),
    [
        ("metadata.rb", 'name "example"\n'),
        ("metadata.json", '{"name": "example"}\n'),
    ],
)
def test_finds_data_bags_from_selected_cookbook_path(
    tmp_path: Path, metadata_name: str, metadata_content: str
) -> None:
    cookbook = tmp_path / "cookbooks" / "example"
    cookbook.mkdir(parents=True)
    (cookbook / metadata_name).write_text(metadata_content)
    bag_dir = tmp_path / "data_bags" / "applications"
    bag_dir.mkdir(parents=True)
    (bag_dir / "web.json").write_text('{"id": "web"}')

    root = ChefPathResolver.resolve_data_bag_root(str(cookbook))
    assert root == tmp_path
    assert root is not None
    items = ChefSubagent._collect_data_bags([root], lambda *_: None)
    assert [item.item_id for item in items] == ["web"]


def test_resolves_data_bag_root_directly(tmp_path: Path) -> None:
    repository = tmp_path / "chef-repository"
    (repository / "data_bags").mkdir(parents=True)

    assert ChefPathResolver.resolve_data_bag_root(str(repository)) == repository


def test_does_not_walk_up_from_an_arbitrary_directory(tmp_path: Path) -> None:
    directory = tmp_path / "arbitrary-directory"
    directory.mkdir()
    (tmp_path / "data_bags").mkdir()

    assert ChefPathResolver.resolve_data_bag_root(str(directory)) is None


def test_returns_no_root_when_cookbook_has_no_data_bags(tmp_path: Path) -> None:
    cookbook = tmp_path / "cookbooks" / "example"
    cookbook.mkdir(parents=True)
    (cookbook / "metadata.rb").write_text('name "example"\n')

    assert ChefPathResolver.resolve_data_bag_root(str(cookbook)) is None


def test_skips_invalid_data_bag_items(tmp_path: Path) -> None:
    bag_dir = tmp_path / "data_bags" / "applications"
    bag_dir.mkdir(parents=True)
    (bag_dir / "valid.json").write_text('{"id": "valid"}')
    (bag_dir / "invalid-json.json").write_text("{")
    (bag_dir / "invalid-type.json").write_text("[]")

    items = ChefSubagent._collect_data_bags([tmp_path], get_logger(__name__))

    assert [item.item_id for item in items] == ["valid"]


def test_collects_each_data_bag_item_once(tmp_path: Path) -> None:
    bag_dir = tmp_path / "data_bags" / "applications"
    bag_dir.mkdir(parents=True)
    (bag_dir / "web.json").write_text('{"id": "web"}')

    items = ChefSubagent._collect_data_bags([tmp_path, tmp_path], lambda *_: None)

    assert [item.item_id for item in items] == ["web"]


def test_expands_loop_over_data_bag_items() -> None:
    recipe_path = "cookbooks/example/recipes/default.rb"
    recipe = RecipeAnalysisResult(
        file_path=recipe_path,
        analysis=RecipeExecutionAnalysis(
            execution_order=[
                ConditionalExecution(
                    condition="data_bag('applications').each do |item_name|",
                    execution_order=[
                        DataBagExecution(data_bag="applications"),
                        ResourceExecution(
                            resource_type="template",
                            name="/etc/applications/#{item['id']}",
                        ),
                    ],
                )
            ]
        ),
    )
    analysis = StructuredAnalysis(
        recipes=[recipe],
        data_bags=[
            DataBagItemAnalysis(
                data_bag="applications",
                item_id="web",
                file_path="data_bags/applications/web.json",
                data={
                    "id": "web",
                    "document_root": "/opt/server/web",
                },
            ),
            DataBagItemAnalysis(
                data_bag="applications",
                item_id="worker",
                file_path="data_bags/applications/worker.json",
                data={"id": "worker", "document_root": "/opt/server/worker"},
            ),
        ],
    )

    tree = ExecutionTreeBuilder(analysis, ChefPathResolver(), ["cookbooks"]).build_tree(
        recipe_path
    )

    loop = tree.children[0]
    assert loop.node_type == "loop"
    assert loop.name == "data_bag('applications')"
    assert [child.name for child in loop.children] == [
        "web",
        "worker",
    ]
    assert loop.children[0].attributes["document_root"] == "/opt/server/web"


def test_data_bag_loop_takes_precedence_over_similar_collection() -> None:
    recipe_path = "cookbooks/example/recipes/default.rb"
    recipe = RecipeAnalysisResult(
        file_path=recipe_path,
        analysis=RecipeExecutionAnalysis(
            execution_order=[
                ConditionalExecution(
                    condition="data_bag('applications').each do |item_name|",
                    execution_order=[
                        ResourceExecution(
                            resource_type="file",
                            name="/etc/applications/#{item_name}",
                        )
                    ],
                )
            ]
        ),
    )
    analysis = StructuredAnalysis(
        recipes=[recipe],
        attribute_collections={"applications": ["attribute-item"]},
        data_bags=[
            DataBagItemAnalysis(
                data_bag="applications",
                item_id="data-bag-item",
                file_path="data_bags/applications/data-bag-item.json",
            )
        ],
    )

    tree = ExecutionTreeBuilder(analysis, ChefPathResolver(), ["cookbooks"]).build_tree(
        recipe_path
    )

    loop = tree.children[0]
    assert loop.name == "data_bag('applications')"
    assert [child.name for child in loop.children] == ["data-bag-item"]
