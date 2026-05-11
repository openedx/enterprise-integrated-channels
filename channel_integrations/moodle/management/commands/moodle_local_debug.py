"""Seed local Moodle audit data and reproduce Moodle client flows with mocked APIs."""

import json

import responses
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand
from enterprise.models import EnterpriseCustomer

from channel_integrations.exceptions import ClientError
from channel_integrations.integrated_channel.models import ApiResponseRecord
from channel_integrations.moodle.client import MoodleAPIClient
from channel_integrations.moodle.models import (
    MoodleEnterpriseCustomerConfiguration,
    MoodleLearnerDataTransmissionAudit,
)


class Command(BaseCommand):
    help = "Seed local Moodle audit records and reproduce grade sync failures with mocked Moodle responses."

    def add_arguments(self, parser):
        parser.add_argument(
            "--seed-records",
            action="store_true",
            help="Seed success and failure Moodle learner audit records.",
        )
        parser.add_argument(
            "--reproduce-404",
            action="store_true",
            help="Run the actual MoodleAPIClient.create_course_completion flow with mocked Moodle responses.",
        )

    def handle(self, *args, **options):
        config = self._get_or_create_local_config()

        if options["seed_records"]:
            self._seed_records(config)

        if options["reproduce_404"]:
            self._reproduce_module_not_found(config)

        if not options["seed_records"] and not options["reproduce_404"]:
            self.stdout.write(self.style.WARNING("No action selected. Use --seed-records and/or --reproduce-404."))

    def _get_or_create_local_config(self):
        site, _ = Site.objects.get_or_create(
            id=1,
            defaults={"domain": "localhost:8000", "name": "localhost"},
        )
        enterprise_customer, _ = EnterpriseCustomer.objects.get_or_create(
            slug="moodle-local",
            defaults={"name": "Moodle Local Enterprise", "site": site},
        )
        config, _ = MoodleEnterpriseCustomerConfiguration.objects.get_or_create(
            enterprise_customer=enterprise_customer,
            defaults={
                "display_name": "Moodle Local",
                "active": True,
                "moodle_base_url": "http://moodle.local",
                "service_short_name": "edx_service",
                "decrypted_token": "local-token",
                "grade_assignment_name": "(edX integration) Final Grade",
            },
        )
        return config

    def _seed_records(self, config):
        scenarios = [
            {
                "enrollment_id": 9001,
                "course_id": "course-v1:DemoX+TST101+2026",
                "status": "404",
                "progress_status": "Passed",
                "friendly": "Moodle grade sync failed: completion course module not found.",
                "error": "Completion course module not found",
                "api_status": 404,
                "api_body": (
                    'MoodleAPIClient request failed: 404 Completion course module not found in Moodle. '
                    'No activity with name="(edX integration) Final Grade" found in course_id=42. '
                    'Available modules: [cmid=101 name="Final Grade" section="General", '
                    'cmid=102 name="Quiz 1" section="Week 1"]. Either create an assignment named '
                    '"(edX integration) Final Grade" in the Moodle course, or set grade_assignment_cmid '
                    'to the cmid of an existing activity.'
                ),
                "is_transmitted": False,
                "grade": 0.95,
                "moodle_date": "2026-04-09",
                "email": "learner@example.com",
                "title": "Demo Course for Moodle Sync",
            },
            {
                "enrollment_id": 9002,
                "course_id": "course-v1:DemoX+TST102+2026",
                "status": "200",
                "progress_status": "Passed",
                "friendly": "Moodle grade sync succeeded.",
                "error": "",
                "api_status": 200,
                "api_body": '{"status":"ok"}',
                "is_transmitted": True,
                "grade": 0.88,
                "moodle_date": "2026-04-10",
                "email": "successful@example.com",
                "title": "Successful Moodle Sync Course",
            },
            {
                "enrollment_id": 9003,
                "course_id": "course-v1:DemoX+TST103+2026",
                "status": "404",
                "progress_status": "In Progress",
                "friendly": "Moodle grade sync failed: user enrollment not found.",
                "error": "User enrollment not found under user=missing@example.com in course=42.",
                "api_status": 404,
                "api_body": (
                    'MoodleAPIClient request failed: 404 User enrollment not found under '
                    'user=missing@example.com in course=42.'
                ),
                "is_transmitted": False,
                "grade": 0.35,
                "moodle_date": "2026-04-11",
                "email": "missing@example.com",
                "title": "Missing Enrollment Demo",
            },
        ]

        for scenario in scenarios:
            api_record = ApiResponseRecord.objects.create(
                status_code=scenario["api_status"],
                body=scenario["api_body"],
            )
            MoodleLearnerDataTransmissionAudit.objects.update_or_create(
                enterprise_course_enrollment_id=scenario["enrollment_id"],
                course_id=scenario["course_id"],
                defaults={
                    "enterprise_customer_uuid": config.enterprise_customer.uuid,
                    "plugin_configuration_id": config.id,
                    "user_email": scenario["email"],
                    "moodle_user_email": scenario["email"],
                    "content_title": scenario["title"],
                    "course_completed": True,
                    "progress_status": scenario["progress_status"],
                    "grade": scenario["grade"],
                    "status": scenario["status"],
                    "error_message": scenario["error"],
                    "friendly_status_message": scenario["friendly"],
                    "api_record": api_record,
                    "is_transmitted": scenario["is_transmitted"],
                    "moodle_completed_timestamp": scenario["moodle_date"],
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {MoodleLearnerDataTransmissionAudit.objects.count()} Moodle learner transmission audits."
            )
        )

    @responses.activate
    def _reproduce_module_not_found(self, config):
        client = MoodleAPIClient(config)
        api_url = client.api_url
        payload = json.dumps({"userID": "learner@example.com", "courseID": "course-v1:DemoX+TST404+2026", "grade": 0.91})

        responses.add(
            responses.GET,
            api_url,
            json={"courses": [{"id": 42}]},
            status=200,
        )
        responses.add(
            responses.GET,
            api_url,
            json=[
                {
                    "name": "General",
                    "modules": [
                        {"id": 101, "name": "Final Grade", "modname": "assign"},
                        {"id": 102, "name": "Quiz 1", "modname": "quiz"},
                    ],
                }
            ],
            status=200,
        )

        try:
            client.create_course_completion("learner@example.com", payload)
        except ClientError as exc:
            self.stdout.write(self.style.WARNING("Actual client flow reproduced the expected failure:"))
            self.stdout.write(f"status_code={exc.status_code}")
            self.stdout.write(exc.message)
            return

        self.stdout.write(self.style.ERROR("Expected MoodleClientError was not raised."))