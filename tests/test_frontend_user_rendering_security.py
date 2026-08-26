from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_node(script: str) -> str:
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def test_exam_publish_student_list_escapes_user_controlled_fields() -> None:
    module_path = ROOT / (
        "static/js/exam-builder/modules/30-media-modal-publish-time-points.js"
    )
    payload = '<img src=x onerror="globalThis.pwned=true">'
    script = f"""
const fs = require('fs');
const vm = require('vm');
const makeElement = () => ({{
  innerHTML: '',
  textContent: '',
  value: '',
  addEventListener: () => undefined,
}});
const elements = {{
  'student-list-container': makeElement(),
  'student-search': makeElement(),
  'selected-count': makeElement(),
}};
const context = {{
  console,
  localStorage: {{ getItem: () => null, setItem: () => undefined }},
  document: {{
    getElementById: (id) => elements[id] || (elements[id] = makeElement()),
    createElement: () => ({{ innerHTML: '', textContent: '' }}),
    addEventListener: () => undefined,
  }},
  examData: {{ questions: [] }},
}};
vm.createContext(context);
vm.runInContext(fs.readFileSync({json.dumps(str(module_path))}, 'utf8'), context);
vm.runInContext(`
  publishState.allStudents = [{{
    id: 7,
    full_name: ${{JSON.stringify({json.dumps(payload)})}},
    username: ${{JSON.stringify({json.dumps(payload)})}},
    student_class: ${{JSON.stringify({json.dumps(payload)})}},
  }}];
  publishState.selectedStudents = [];
  renderStudentList();
`, context);
process.stdout.write(elements['student-list-container'].innerHTML);
"""

    rendered = _run_node(script)

    assert payload not in rendered
    assert rendered.count("&lt;img") == 3


def test_monitoring_student_table_escapes_user_and_device_fields() -> None:
    module_path = ROOT / (
        "static/js/admin/monitoring/modules/10-pause-websocket-student-detail.js"
    )
    payload = '<img src=x onerror="globalThis.pwned=true">'
    script = f"""
const fs = require('fs');
const vm = require('vm');
const makeElement = () => ({{
  innerHTML: '',
  textContent: '',
  value: '',
  style: {{}},
  dataset: {{}},
  classList: {{ add: () => undefined, remove: () => undefined, toggle: () => undefined }},
  addEventListener: () => undefined,
}});
const elements = {{
  'exam-filter': makeElement(),
  'session-students-tbody': makeElement(),
}};
const context = {{
  console,
  document: {{
    getElementById: (id) => elements[id] || (elements[id] = makeElement()),
    querySelectorAll: () => [],
  }},
  currentExamIdForModal: 11,
  sessionTableSearchTerm: '',
  sessionTableStatusFilter: 'all',
  studentConnectionStatus: {{}},
  getMonitorStudentKey: () => 'student-key',
  _escapeJsString: (value) => String(value ?? '').replace(/'/g, "\\\\'"),
  escapeHtml: (value) => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\"/g, '&quot;')
    .replace(/'/g, '&#39;'),
}};
vm.createContext(context);
const source = fs.readFileSync({json.dumps(str(module_path))}, 'utf8');
const renderStart = source.indexOf('function renderStudentTable');
const renderEnd = source.indexOf('// Update last update time', renderStart);
vm.runInContext(source.slice(renderStart, renderEnd), context);
vm.runInContext(`
  renderStudentTable([{{
    student: {{
      id: 7,
      full_name: ${{JSON.stringify({json.dumps(payload)})}},
      username: ${{JSON.stringify({json.dumps(payload)})}},
      student_class: ${{JSON.stringify({json.dumps(payload)})}},
    }},
    session: {{ id: 9, status: 'in_progress', is_online: false }},
    status: 'active',
    statusLabel: 'Sedang Ujian',
    deviceInfo: ${{JSON.stringify({json.dumps(payload)})}},
    violationsCount: 0,
  }}]);
`, context);
process.stdout.write(elements['session-students-tbody'].innerHTML);
"""

    rendered = _run_node(script)

    assert payload not in rendered
    assert rendered.count("&lt;img") >= 5
