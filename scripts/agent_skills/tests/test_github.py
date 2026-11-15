import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from agent_skills import CliError, cli
from agent_skills.github import GitHub, parse_remote
from fakes import FakeRunner, names_repo, with_origin


class ParseRemoteTest(unittest.TestCase):
    def test_https_with_git_suffix(self) -> None:
        self.assertEqual(parse_remote("https://github.com/julian-perge/agent-skills.git"), "julian-perge/agent-skills")

    def test_https_without_git_suffix(self) -> None:
        self.assertEqual(parse_remote("https://github.com/julian-perge/urchin"), "julian-perge/urchin")

    def test_https_with_user_and_trailing_slash(self) -> None:
        self.assertEqual(parse_remote("https://someone@github.com/julian-perge/urchin/"), "julian-perge/urchin")

    def test_scp_style_ssh(self) -> None:
        self.assertEqual(parse_remote("git@github.com:julian-perge/agent-skills.git"), "julian-perge/agent-skills")

    def test_ssh_url(self) -> None:
        self.assertEqual(parse_remote("ssh://git@github.com/julian-perge/agent-skills.git"), "julian-perge/agent-skills")

    def test_repo_name_with_dots_and_dashes(self) -> None:
        self.assertEqual(
            parse_remote("git@github.com:julian-perge/blender-addon-rs317-667mqo-makeup.git"),
            "julian-perge/blender-addon-rs317-667mqo-makeup",
        )

    def test_local_path_is_an_error(self) -> None:
        with self.assertRaises(CliError) as caught:
            parse_remote("/Users/someone/repo")
        self.assertEqual(caught.exception.code, 2)


class RepoTest(unittest.TestCase):
    def test_repo_comes_from_origin(self) -> None:
        runner = with_origin(FakeRunner())
        self.assertEqual(GitHub(runner).repo, "julian-perge/agent-skills")
        self.assertEqual(runner.calls, [["git", "remote", "get-url", "origin"]])

    def test_explicit_repo_skips_git(self) -> None:
        runner = FakeRunner()
        self.assertEqual(GitHub(runner, "julian-perge/urchin").repo, "julian-perge/urchin")
        self.assertEqual(runner.calls, [])

    def test_outside_a_repo_is_an_environment_error(self) -> None:
        runner = FakeRunner().on(
            "git", "remote", "get-url", "origin",
            returncode=128, stderr="fatal: not a git repository (or any of the parent directories): .git\n",
        )
        with self.assertRaises(CliError) as caught:
            _ = GitHub(runner).repo
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("not a git repository", str(caught.exception))

    def test_no_origin_is_an_environment_error(self) -> None:
        runner = FakeRunner().on("git", "remote", "get-url", "origin", returncode=2, stderr="error: No such remote 'origin'\n")
        with self.assertRaises(CliError) as caught:
            _ = GitHub(runner).repo
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("--repo", str(caught.exception))


class GraphqlTest(unittest.TestCase):
    def test_graphql_names_the_origin_repo_and_types_numbers(self) -> None:
        runner = with_origin(FakeRunner()).on("gh", "api", "graphql", stdout=json.dumps({"data": {"repository": {}}}))
        GitHub(runner).graphql("query($owner: String!, $name: String!, $number: Int!) { x }", number=49)
        call = runner.gh_calls()[0]
        self.assertTrue(names_repo(call, "julian-perge/agent-skills"))
        self.assertEqual(call[call.index("number=49") - 1], "-F")

    def test_graphql_leaves_out_none_variables(self) -> None:
        runner = FakeRunner().on("gh", "api", "graphql", stdout=json.dumps({"data": {"repository": {}}}))
        GitHub(runner, "julian-perge/urchin").graphql("query { x }", after=None)
        self.assertFalse(any(arg.startswith("after=") for arg in runner.gh_calls()[0]))

    def test_missing_gh_is_an_environment_error(self) -> None:
        runner = FakeRunner(missing=frozenset({"gh"}))
        with self.assertRaises(CliError) as caught:
            GitHub(runner, "julian-perge/urchin").graphql("query { x }")
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("gh", str(caught.exception))

    def test_signed_out_gh_is_an_environment_error(self) -> None:
        runner = FakeRunner().on(
            "gh", "api", "graphql", returncode=4,
            stderr="To get started with GitHub CLI, please run:  gh auth login\n",
        )
        with self.assertRaises(CliError) as caught:
            GitHub(runner, "julian-perge/urchin").graphql("query { x }")
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("gh auth login", str(caught.exception))

    def test_api_error_is_an_environment_error(self) -> None:
        runner = FakeRunner().on(
            "gh", "api", "graphql", returncode=1,
            stderr="gh: Could not resolve to an Issue with the number of 99999.\n",
        )
        with self.assertRaises(CliError) as caught:
            GitHub(runner, "julian-perge/urchin").graphql("query { x }")
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("Could not resolve", str(caught.exception))


class CliExitCodeTest(unittest.TestCase):
    def run_cli(self, argv: list[str], runner: FakeRunner) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv, runner)
        return code, out.getvalue(), err.getvalue()

    def test_help_exits_0(self) -> None:
        code, out, _ = self.run_cli(["--help"], FakeRunner())
        self.assertEqual(code, 0)
        self.assertIn("usage: agent-skills", out)

    def test_no_verb_is_a_usage_error(self) -> None:
        code, _, err = self.run_cli([], FakeRunner())
        self.assertEqual(code, 2)
        self.assertIn("usage: agent-skills", err)

    def test_malformed_repo_is_a_usage_error(self) -> None:
        code, _, err = self.run_cli(["--repo", "urchin", "--help"], FakeRunner())
        self.assertEqual(code, 2)
        self.assertIn("OWNER/REPO", err)


if __name__ == "__main__":
    unittest.main()
