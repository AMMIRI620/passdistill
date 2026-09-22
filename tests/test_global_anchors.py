import unittest
from pathlib import Path
from passdistill.agents.catalog import load_static_catalog
from passdistill.pipeline import PipelineEditor


class GlobalAnchorTests(unittest.TestCase):
    def edit(self, pipeline, edit):
        return PipelineEditor(pipeline, catalog=load_static_catalog(Path.cwd()).for_prompt()).apply_candidate({"edits": [edit]})

    def test_replace_and_insert_in_later_manager(self):
        pipeline = 'function(instcombine),function(loop-distribute,loop-vectorize)'
        for kind in ('replace_region', 'insert_fragment'):
            target = {'parent_manager': 'function', 'anchor': 'loop-vectorize#1', 'start_anchor': 'loop-vectorize#1', 'end_anchor': 'loop-vectorize#1', 'position': 'before'}
            result = self.edit(pipeline, {'type': kind, 'target': target, 'replacement': [{'kind': 'pass', 'name': 'gvn'}]})
            self.assertTrue(result.valid, result.invalid_errors)
            self.assertTrue(result.pipeline.startswith('function(instcombine),function(loop-distribute,gvn'))

    def test_repeated_anchor_is_global_and_manager_is_constraint(self):
        pipeline = 'function(instcombine),function(instcombine)'
        target = {'parent_manager': 'function', 'parent_occurrence': 2, 'start_anchor': 'instcombine#2', 'end_anchor': 'instcombine#2'}
        edit = {'type': 'replace_region', 'target': target, 'replacement': [{'kind': 'pass', 'name': 'gvn'}]}
        self.assertEqual(self.edit(pipeline, edit).pipeline, 'function(instcombine),function(gvn)')
        target['parent_occurrence'] = 1
        self.assertFalse(self.edit(pipeline, edit).valid)

    def test_cross_manager_region_rejected(self):
        result = self.edit('function(instcombine),function(gvn)', {'type': 'replace_region', 'target': {'start_anchor': 'instcombine#1', 'end_anchor': 'gvn#1'}, 'replacement': []})
        self.assertFalse(result.valid)

    def test_parameter_string_is_validated(self):
        edit = {'type': 'set_pass_parameter', 'target': {'anchor': 'loop-vectorize#1'}, 'parameters': 'no-interleave-forced-only;no-vectorize-forced-only'}
        self.assertTrue(self.edit('function(loop-vectorize)', edit).valid)
        edit['parameters'] = 'vectorize-forced-only=False'
        self.assertFalse(self.edit('function(loop-vectorize)', edit).valid)

    def test_move_repeated_node_preserves_destination(self):
        result = self.edit('function(instcombine,gvn,instcombine,sroa)', {'type': 'move_node', 'target': {'source_anchor': 'instcombine#1', 'dest_anchor': 'instcombine#2', 'position': 'after'}})
        self.assertTrue(result.valid, result.invalid_errors)
        self.assertEqual(result.pipeline, 'function(gvn,instcombine,instcombine,sroa)')


if __name__ == '__main__':
    unittest.main()
