from self_healing_agent.retrieval.document_builder import _create_parent_incident_db_entries


def test_create_parent_incident_db_entries_normalizes_nullable_array_fields():
    entries, errors = _create_parent_incident_db_entries(
        [
            {
                "incident_id": "INC-1",
                "incident_type": "Host Infrastructure",
                "service_domain": "PAYMENTS",
                "datacenter": "AWSE",
                "app_name": "my-app",
                "hosts": None,
                "incident_reason": "CPU high",
                "metric_names": ["cpu"],
                "instances": None,
                "instance_hosts": None,
                "warnings": None,
                "incident_text_raw": "{\"INCIDENT_ID\":\"INC-1\"}",
                "incident_reason_normalized": "payments service.",
                "closure_remarks": "",
                "normalized_reason_hash": "hash-1",
                "created_date": None,
                "updated_date": None,
            }
        ]
    )

    assert errors == []
    assert entries[0]["hosts"] == []
    assert entries[0]["instances"] == []
    assert entries[0]["instance_hosts"] == []
    assert entries[0]["warnings"] == []
