from django.test import SimpleTestCase

from api.services.tech_stack_detector import (
    UnsupportedTechStackError,
    detect_tech_stack,
)


class TechStackDetectorTests(SimpleTestCase):
    def test_detects_maven_spring_boot(self):
        stack = detect_tech_stack({"pom.xml": "<project></project>"})

        self.assertEqual(stack.technology, "SPRING_BOOT")
        self.assertEqual(stack.build_tool, "MAVEN")
        self.assertEqual(stack.port, 8080)

    def test_detects_gradle_spring_boot(self):
        stack = detect_tech_stack({"build.gradle": "plugins { id 'java' }"})

        self.assertEqual(stack.technology, "SPRING_BOOT")
        self.assertEqual(stack.build_tool, "GRADLE")

    def test_detects_react_from_package_json(self):
        stack = detect_tech_stack({"package.json": '{"dependencies":{"react":"18.3.1"}}'})

        self.assertEqual(stack.technology, "REACT")
        self.assertEqual(stack.build_tool, "NPM")
        self.assertEqual(stack.port, 3000)

    def test_detects_node_from_package_json(self):
        stack = detect_tech_stack({"package.json": '{"dependencies":{"express":"4.21.2"}}'})

        self.assertEqual(stack.technology, "NODE_JS")
        self.assertEqual(stack.port, 3000)

    def test_detects_python_from_requirements(self):
        stack = detect_tech_stack({"requirements.txt": "Django>=5.0"})

        self.assertEqual(stack.technology, "PYTHON")
        self.assertEqual(stack.build_tool, "PIP")
        self.assertEqual(stack.port, 8000)

    def test_rejects_unknown_repository(self):
        with self.assertRaises(UnsupportedTechStackError):
            detect_tech_stack({"README.md": "Unknown application"})
