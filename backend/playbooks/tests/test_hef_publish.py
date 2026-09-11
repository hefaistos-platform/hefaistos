"""Tests for the OpenTIDE HEF publish helpers and worker happy path.

These tests focus on the pieces that wire compile/commit/deploy together:

- :func:`playbooks.hef_publish.compile_opentide_bundle` produces the expected
  three-file YAML bundle (TVM/DOM/MDR) and surfaces validation errors.
- :func:`playbooks.hef_publish.extract_github_details` correctly parses the
  HTTPS and SSH GitHub URL flavours we support.
- :func:`playbooks.hef_publish.create_github_commit` performs the Git Data API
  dance (read ref → blobs → tree → commit → update ref) and raises on the
  documented error paths.

Mocks are used heavily so the tests do not require a populated database or a
live GitHub instance.  ``compile_opentide_bundle`` performs lazy imports inside
the function body so patches must target the *source* modules rather than the
``playbooks.hef_publish`` namespace.
"""

import contextlib
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from playbooks.hef_publish import (
    compile_opentide_bundle,
    compile_platform_rule_files,
    create_github_commit,
    extract_github_details,
    join_repo_path,
)


class TestExtractGithubDetails(SimpleTestCase):
    def test_https_url(self):
        self.assertEqual(
            extract_github_details('https://github.com/acme/repo'),
            ('acme', 'repo'),
        )

    def test_https_url_with_dot_git_suffix(self):
        self.assertEqual(
            extract_github_details('https://github.com/acme/repo.git'),
            ('acme', 'repo'),
        )

    def test_ssh_url(self):
        self.assertEqual(
            extract_github_details('git@github.com:acme/repo.git'),
            ('acme', 'repo'),
        )

    def test_returns_none_on_unknown_url(self):
        self.assertIsNone(extract_github_details(''))
        self.assertIsNone(extract_github_details(None))
        self.assertIsNone(extract_github_details('https://gitlab.com/acme/repo'))


class TestJoinRepoPath(SimpleTestCase):
    def test_strips_leading_and_trailing_slashes(self):
        self.assertEqual(
            join_repo_path('/content/', '/Objects/', 'Threat Vectors', 'foo.yaml'),
            'content/Objects/Threat Vectors/foo.yaml',
        )

    def test_skips_empty_parts(self):
        self.assertEqual(
            join_repo_path('', 'Objects/Detection Rules', 'mdr.yaml'),
            'Objects/Detection Rules/mdr.yaml',
        )


def _bundle_patches(validation_errors=None):
    """Return a list of patches for :func:`compile_opentide_bundle` dependencies.

    ``compile_opentide_bundle`` imports its collaborators lazily, so each
    patch must target the *defining* module rather than ``playbooks.hef_publish``.
    """
    validation_errors = validation_errors or {'tvm': [], 'dom': [], 'mdr': []}
    return [
        patch(
            'playbooks.utils.opentide_compiler.compile_tvm_yaml',
            return_value={'name': 'tvm_test'},
        ),
        patch(
            'playbooks.utils.opentide_compiler.compile_dom_yaml',
            return_value={'name': 'dom_test'},
        ),
        patch(
            'playbooks.utils.opentide_compiler.compile_mdr_yaml',
            return_value={'name': 'mdr_test'},
        ),
        patch(
            'playbooks.utils.opentide_compiler.compile_bdr_yaml_with_ai',
            return_value=None,
        ),
        patch(
            'playbooks.utils.opentide_compiler._normalize_mdr_impacted_entities',
            return_value=None,
        ),
        patch(
            'playbooks.utils.opentide_compiler.dump_opentide_yaml',
            side_effect=lambda data: f"name: {data['name']}\n",
        ),
        patch(
            'playbooks.utils.opentide_validator.validate_tvm_structure',
            return_value=(not validation_errors['tvm'], validation_errors['tvm']),
        ),
        patch(
            'playbooks.utils.opentide_validator.validate_dom_structure',
            return_value=(not validation_errors['dom'], validation_errors['dom']),
        ),
        patch(
            'playbooks.utils.opentide_validator.validate_mdr_structure',
            return_value=(not validation_errors['mdr'], validation_errors['mdr']),
        ),
    ]


class TestCompileOpenTideBundle(SimpleTestCase):
    """Happy path and validation-error path for :func:`compile_opentide_bundle`."""

    def test_returns_three_yaml_files_in_canonical_folders(self):
        playbook = MagicMock()
        playbook.title = 'My Playbook'

        with contextlib.ExitStack() as stack:
            for cm in _bundle_patches():
                stack.enter_context(cm)
            bundle, errors = compile_opentide_bundle(playbook, target_folder='content/hef')

        self.assertEqual(errors, [])
        self.assertIsNotNone(bundle)
        files = bundle['files']
        self.assertEqual(set(files.keys()), {
            'content/hef/Objects/Threat Vectors/My_Playbook_tvm.yaml',
            'content/hef/Objects/Detection Objectives/My_Playbook_dom.yaml',
            'content/hef/Objects/Detection Rules/My_Playbook_mdr.yaml',
        })
        self.assertEqual(
            bundle['primary_path'],
            'content/hef/Objects/Detection Rules/My_Playbook_mdr.yaml',
        )
        self.assertEqual(bundle['mdr_yaml'], 'name: mdr_test\n')
        self.assertIsNone(bundle['bdr_path'])

    def test_returns_validation_errors_when_mdr_invalid(self):
        playbook = MagicMock()
        playbook.title = 'My Playbook'

        with contextlib.ExitStack() as stack:
            for cm in _bundle_patches(validation_errors={
                'tvm': [],
                'dom': [],
                'mdr': ['response.alert_severity is required'],
            }):
                stack.enter_context(cm)
            bundle, errors = compile_opentide_bundle(playbook)

        self.assertIsNone(bundle)
        self.assertEqual(errors, ['MDR: response.alert_severity is required'])


class TestCompilePlatformRuleFiles(SimpleTestCase):
    @patch('rules.utils.extract_platform_rules_from_opentide')
    @patch('playbooks.utils.opentide_compiler.compile_mdr_yaml')
    def test_uses_mdr_metadata_title_for_filenames(self, mock_compile_mdr_yaml, mock_extract_platform_rules):
        playbook = MagicMock()
        playbook.id = 'playbook-1'
        mock_compile_mdr_yaml.return_value = {
            'name': 'mdr_my_playbook',
            'metadata': {'title': 'My Playbook'},
        }
        mock_extract_platform_rules.return_value = {
            'content/hef/sigma/my_playbook.yml': 'title: My Playbook\n',
        }

        bundle, errors = compile_platform_rule_files(playbook, target_folder='content/hef')

        self.assertEqual(errors, [])
        self.assertEqual(
            bundle,
            {
                'files': {
                    'content/hef/sigma/my_playbook.yml': 'title: My Playbook\n',
                },
                'primary_path': 'content/hef/sigma/my_playbook.yml',
            },
        )
        # Verify sanitized_title passed to extractor was derived from metadata.title
        call_kwargs = mock_extract_platform_rules.call_args
        self.assertEqual(call_kwargs.kwargs.get('sanitized_title') or call_kwargs.args[2], 'My_Playbook_mdr')

    @patch('rules.utils.extract_platform_rules_from_opentide')
    @patch('playbooks.utils.opentide_compiler.compile_mdr_yaml')
    def test_falls_back_to_mdr_name_when_no_metadata_title(self, mock_compile_mdr_yaml, mock_extract_platform_rules):
        playbook = MagicMock()
        playbook.id = 'playbook-1'
        mock_compile_mdr_yaml.return_value = {'name': 'mdr_fallback_rule'}
        mock_extract_platform_rules.return_value = {
            'kql/mdr_fallback_rule.kql': 'DeviceProcessEvents | limit 10',
        }

        bundle, errors = compile_platform_rule_files(playbook, target_folder='')

        self.assertEqual(errors, [])
        call_kwargs = mock_extract_platform_rules.call_args
        self.assertEqual(
            call_kwargs.kwargs.get('sanitized_title') or call_kwargs.args[2],
            'mdr_fallback_rule_mdr',
        )


class TestCreateGithubCommit(SimpleTestCase):
    """Verify the Git Data API choreography in :func:`create_github_commit`."""

    @patch('playbooks.hef_publish.requests')
    def test_full_happy_path_calls_all_endpoints(self, mock_requests):
        ref_resp = MagicMock(status_code=200)
        ref_resp.json.return_value = {'object': {'sha': 'base-commit-sha'}}
        commit_resp = MagicMock(status_code=200)
        commit_resp.json.return_value = {'tree': {'sha': 'base-tree-sha'}}
        blob_resp = MagicMock(status_code=201)
        blob_resp.json.return_value = {'sha': 'blob-sha'}
        tree_resp = MagicMock(status_code=201)
        tree_resp.json.return_value = {'sha': 'new-tree-sha'}
        new_commit_resp = MagicMock(status_code=201)
        new_commit_resp.json.return_value = {'sha': 'new-commit-sha'}
        patch_ref_resp = MagicMock(status_code=200)
        patch_ref_resp.json.return_value = {}

        mock_requests.get.side_effect = [ref_resp, commit_resp]
        mock_requests.post.side_effect = [blob_resp, tree_resp, new_commit_resp]
        mock_requests.patch.return_value = patch_ref_resp

        sha = create_github_commit(
            repo_owner='acme',
            repo_name='repo',
            branch='main',
            github_token='token',
            files={'foo.yaml': 'name: foo\n'},
            commit_message='ci: hef publish',
        )

        self.assertEqual(sha, 'new-commit-sha')
        self.assertEqual(mock_requests.get.call_count, 2)
        # 1 blob + tree + new commit.
        self.assertEqual(mock_requests.post.call_count, 3)
        mock_requests.patch.assert_called_once()

    @patch('playbooks.hef_publish.requests')
    def test_raises_when_branch_missing(self, mock_requests):
        ref_resp = MagicMock(status_code=404)
        ref_resp.json.return_value = {'message': 'Not Found'}
        ref_resp.text = 'Not Found'
        mock_requests.get.return_value = ref_resp

        with self.assertRaises(ValueError) as cm:
            create_github_commit(
                repo_owner='acme',
                repo_name='repo',
                branch='missing',
                github_token='token',
                files={'a.yaml': 'a: 1\n'},
                commit_message='ci',
            )
        self.assertIn('Unable to access branch missing', str(cm.exception))
