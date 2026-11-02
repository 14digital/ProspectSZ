import test from "node:test";import assert from "node:assert/strict";import fs from "node:fs";
test("six required pages exist",()=>{for(const page of ["dashboard","discovery","prospects","outreach","followups","settings"])assert.ok(fs.existsSync(`app/${page}/page.tsx`))});
