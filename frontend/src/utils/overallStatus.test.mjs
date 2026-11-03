/* global console */
import assert from "node:assert/strict";
import { DEPARTMENT_GUIDES } from "../data/departmentGuides.js";
import { getOverallStatus } from "./overallStatus.js";

const ready = { score: 96, status: "Ready for Submission", results: [] };
const outpatientSteps = DEPARTMENT_GUIDES.outpatient.steps;
const completeOutpatient = {
  completed: Object.fromEntries(outpatientSteps.filter((step) => step.required).map((step) => [step.title, true])),
  signedOffAt: "2026-11-02T10:00:00.000Z",
};

let overall = getOverallStatus({ ...ready, department: "outpatient" }, { completed: {}, signedOffAt: null });
assert.equal(overall.status, "amber");
assert.equal(overall.label, "Awaiting department sign-off");
assert.match(overall.reason, /Outpatient: 0 of 3 required items done/);

overall = getOverallStatus({ ...ready, department: "outpatient" }, completeOutpatient);
assert.equal(overall.status, "green");
assert.equal(overall.label, "Ready");

overall = getOverallStatus({ score: 72, status: "Needs Review", results: [], department: "outpatient" }, { completed: {}, signedOffAt: null });
assert.equal(overall.status, "amber");
assert.equal(overall.label, "Needs review");

overall = getOverallStatus({ score: 95, status: "Ready for Submission", results: [{ passed: false, severity: "error" }], department: "outpatient" }, completeOutpatient);
assert.equal(overall.status, "red");
assert.equal(overall.label, "Blocked");

overall = getOverallStatus({ ...ready, department: "unassigned" }, { completed: {}, signedOffAt: null });
assert.equal(overall.status, "green");
assert.equal(overall.label, "Ready");

const withOptionalIncomplete = {
  ...completeOutpatient,
  completed: { ...completeOutpatient.completed, [outpatientSteps.find((step) => !step.required).title]: false },
};
overall = getOverallStatus({ ...ready, department: "outpatient" }, withOptionalIncomplete);
assert.equal(overall.status, "green");

const signOffRevokedAfterEdit = { ...completeOutpatient, signedOffAt: null, signedOffBy: "" };
overall = getOverallStatus({ ...ready, department: "outpatient" }, signOffRevokedAfterEdit);
assert.equal(overall.status, "amber");
assert.equal(overall.label, "Awaiting department sign-off");
assert.match(overall.reason, /sign-off is missing/);

console.log("overallStatus tests passed (7 cases)");

