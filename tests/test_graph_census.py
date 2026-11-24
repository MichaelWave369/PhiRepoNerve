import copy
import tempfile
import unittest
from pathlib import Path

from phireponerve.graph_census import census, read_json

NOW = "2026-11-23T00:00:00Z"


def inventory():
    return dict(schemaVersion=1, source="PhiRepoNerve", scope="public-ids-only",
                owner="MichaelWave369", observedAt=NOW,
                repositories=[dict(id=str(i), pushedAt=None, archived=False) for i in range(1, 5)])


def edge(i, a, b, kind="code-bridge", status="verified"):
    return dict(id=str(i), **{"from": f"github:{a}", "to": f"github:{b}"},
                kind=kind, status=status, direction="directed",
                summary="Synthetic example", scope="Source only", reviewedAt=NOW,
                evidence=[dict(url="https://github.com/MichaelWave369/Example/blob/" +
                               "a" * 40 + "/README.md#L1-L2", claim="Fixture")])


def ledger():
    return dict(schemaVersion=1, owner="MichaelWave369", reviewedAt=NOW, coverage="Fixture",
                relationships=[edge(1, 1, 2), edge(2, 2, 1, "navigation"),
                               edge(3, 2, 3, "documented-integration", "documented")])


class GraphCensusTests(unittest.TestCase):
    def test_metrics_deduplicate_pairs_and_retain_grades(self):
        r = census(inventory(), ledger())
        self.assertEqual(r["nodes"], 4)
        self.assertEqual(r["relationship_records"], 3)
        self.assertEqual(r["unique_undirected_pairs"], 2)
        self.assertEqual(r["possible_undirected_pairs"], 6)
        self.assertAlmostEqual(r["recorded_pair_density"], 1 / 3)
        self.assertEqual(r["mean_recorded_degree"], 1)
        self.assertEqual(r["nodes_without_recorded_edges"], 1)
        self.assertEqual(r["weak_component_count"], 2)
        self.assertEqual(r["largest_weak_component"], 3)
        self.assertEqual(r["by_reported_grade"], {"documented": 1, "verified": 2})
        self.assertEqual(r["authority"], "NONE")

    def test_field_constellation_shared_library_shape(self):
        l = ledger()
        shared = edge(4, 3, 4, "shared-library")
        shared.update(direction="undirected", library="React / react-dom")
        shared["evidence"] = [
            dict(url="https://github.com/MichaelWave369/A/blob/" + "a" * 40 +
                 "/package.json#L1-L2", claim="Fixture A"),
            dict(url="https://github.com/MichaelWave369/B/blob/" + "b" * 40 +
                 "/package.json#L1-L2", claim="Fixture B"),
        ]
        l["relationships"].append(shared)
        r = census(inventory(), l)
        self.assertEqual(r["by_kind"]["shared-library"], 1)
        self.assertEqual(r["unique_undirected_pairs"], 3)
        for value in (None, "", " ", 42):
            bad = copy.deepcopy(l)
            bad["relationships"][-1]["library"] = value
            with self.assertRaises(ValueError):
                census(inventory(), bad)
        missing = copy.deepcopy(l)
        del missing["relationships"][-1]["library"]
        with self.assertRaises(ValueError):
            census(inventory(), missing)
        l["relationships"][0]["library"] = "Not a shared-library record"
        with self.assertRaises(ValueError):
            census(inventory(), l)

    def test_empty_and_singleton(self):
        for count in (0, 1):
            i, l = inventory(), ledger()
            i["repositories"] = i["repositories"][:count]
            l["relationships"] = []
            r = census(i, l)
            self.assertIsNone(r["recorded_pair_density"])
            self.assertEqual(r["weak_component_count"], count)
            self.assertEqual(r["nodes_without_recorded_edges"], count)

    def test_rejects_unknown_self_duplicate_unpinned_and_extra_keys(self):
        for mutation in (
            lambda l: l["relationships"][0].update({"to": "github:99"}),
            lambda l: l["relationships"][0].update({"to": "github:1"}),
            lambda l: l["relationships"].append(copy.deepcopy(l["relationships"][0])),
            lambda l: l["relationships"].append(dict(l["relationships"][0], id="new")),
            lambda l: l["relationships"][0]["evidence"][0].update(url="https://github.com/MichaelWave369/Example/blob/main/README.md"),
            lambda l: l["relationships"][0].update(execute=True),
            lambda l: l["relationships"][0].update(status="runtime-proven"),
        ):
            l = ledger()
            mutation(l)
            with self.assertRaises(ValueError):
                census(inventory(), l)

    def test_rejects_private_or_duplicate_inventory(self):
        for mutation in (
            lambda i: i.update(scope="private"),
            lambda i: i["repositories"][0].update(private=True),
            lambda i: i["repositories"].append(i["repositories"][0]),
            lambda i: i.update(schemaVersion=True),
        ):
            i = inventory()
            mutation(i)
            with self.assertRaises(ValueError):
                census(i, ledger())

    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.json"
            p.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_json(p)


if __name__ == "__main__":
    unittest.main()
