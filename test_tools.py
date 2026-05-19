import csv
import os
import tempfile
import unittest

from tools import dispatch_tool, list_files, read_file


class TestReadFileCSV(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        )
        writer = csv.writer(self.tmp)
        writer.writerow(["name", "score"])
        writer.writerow(["alice", "42"])
        writer.writerow(["bob", "99"])
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_reads_csv_content(self):
        result = read_file(self.tmp.name)
        self.assertIn("name\tscore", result)
        self.assertIn("alice\t42", result)
        self.assertIn("bob\t99", result)

    def test_truncates_when_max_chars_exceeded(self):
        result = read_file(self.tmp.name, max_chars=5)
        self.assertIn("truncated", result)


class TestReadFileMissing(unittest.TestCase):
    def test_missing_file_returns_error_string(self):
        result = read_file("/nonexistent/path/file.csv")
        self.assertIn("Error", result)
        self.assertIn("/nonexistent/path/file.csv", result)


class TestListFiles(unittest.TestCase):
    def test_lists_current_directory(self):
        result = list_files(".")
        self.assertIn("tools.py", result)

    def test_lists_directory_shows_sizes(self):
        result = list_files(".")
        # At least one entry should show "bytes"
        self.assertIn("bytes", result)

    def test_missing_directory_returns_error(self):
        result = list_files("/nonexistent/directory")
        self.assertIn("Error", result)


class TestDispatchToolUnknown(unittest.TestCase):
    def test_unknown_tool_returns_error_string(self):
        result = dispatch_tool("nonexistent_tool", {})
        self.assertIn("Unknown tool", result)
        self.assertIn("nonexistent_tool", result)


if __name__ == "__main__":
    unittest.main()
