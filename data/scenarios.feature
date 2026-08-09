Feature: Ticket ID Resolution
  As a user
  I want to use partial ticket IDs
  So that I can work faster without typing full IDs

  Background:
    Given a clean tickets directory

  Scenario: Exact ID match
    Given a ticket exists with ID "abc-1234"
    When I run "ticket show abc-1234"
    Then the command should succeed
    And the output should contain "id: abc-1234"

  Scenario: Partial ID match by suffix
    Given a ticket exists with ID "abc-1234"
    When I run "ticket show 1234"
    Then the command should succeed
    And the output should contain "id: abc-1234"

  Scenario: Partial ID match by prefix
    Given a ticket exists with ID "abc-1234"
    When I run "ticket show abc"
    Then the command should succeed
    And the output should contain "id: abc-1234"

  Scenario: Partial ID match by substring
    Given a ticket exists with ID "abc-1234"
    When I run "ticket show c-12"
    Then the command should succeed
    And the output should contain "id: abc-1234"

  Scenario: Ambiguous ID error
    Given a ticket exists with ID "abc-1234"
    And a ticket exists with ID "abc-5678"
    When I run "ticket show abc"
    Then the command should fail
    And the output should contain "Error: ambiguous ID 'abc' matches multiple tickets"

  Scenario: Non-existent ID error
    When I run "ticket show nonexistent"
    Then the command should fail
    And the output should contain "Error: ticket 'nonexistent' not found"

  Scenario: Exact match takes precedence
    Given a ticket exists with ID "abc"
    And a ticket exists with ID "abc-1234"
    When I run "ticket show abc"
    Then the command should succeed
    And the output should contain "id: abc"
    And the output should contain "Short ID ticket"

  Scenario: ID resolution works with status command
    Given a ticket exists with ID "test-9999"
    When I run "ticket status 9999 in_progress"
    Then the command should succeed
    And ticket "test-9999" should have field "status" with value "in_progress"

  Scenario: ID resolution works with dep command
    Given a ticket exists with ID "dep-aaaa"
    And a ticket exists with ID "dep-bbbb"
    When I run "ticket dep aaaa bbbb"
    Then the command should succeed
    And ticket "dep-aaaa" should have "bbbb" in deps

  Scenario: ID resolution works with link command
    Given a ticket exists with ID "link-cccc"
    And a ticket exists with ID "link-dddd"
    When I run "ticket link cccc dddd"
    Then the command should succeed
    And ticket "link-cccc" should have "link-dddd" in links

Feature: Ticket Creation
  As a user
  I want to create tickets with various options
  So that I can track tasks in my project

  Background:
    Given a clean tickets directory

  Scenario: Create a basic ticket with name
    When I run "ticket create 'My first ticket'"
    Then the command should succeed
    And the output should match a ticket ID pattern
    And a ticket file should exist

  Scenario: Create a ticket with default name
    When I run "ticket create"
    Then the command should succeed
    And the output should match a ticket ID pattern
    And a ticket file should exist

  Scenario: Create a ticket with description
    When I run "ticket create 'Test ticket' -d 'This is the description'"
    Then the command should succeed
    And the created ticket should contain "This is the description"

  Scenario: Create a ticket with type
    When I run "ticket create 'Bug ticket' -t bug"
    Then the command should succeed
    And the created ticket should have field "type" with value "bug"

  Scenario: Create a ticket with priority
    When I run "ticket create 'High priority' -p 0"
    Then the command should succeed
    And the created ticket should have field "priority" with value "0"

  Scenario: Create a ticket with assignee
    When I run "ticket create 'Assigned ticket' -a 'John Doe'"
    Then the command should succeed
    And the created ticket should have field "assignee" with value "John Doe"

  Scenario: Create a ticket with external reference
    When I run "ticket create 'External ticket' --external-ref 'JIRA-123'"
    Then the command should succeed
    And the created ticket should have field "external-ref" with value "JIRA-123"

  Scenario: Create a ticket with parent
    Given a ticket exists with ID "parent-001"
    When I run "ticket create 'Child ticket' --parent parent-001"
    Then the command should succeed
    And the created ticket should have field "parent" with value "parent-001"

  Scenario: Create a ticket with design notes
    When I run "ticket create 'Design ticket' --design 'Use microservices'"
    Then the command should succeed
    And the created ticket should contain "## Design"
    And the created ticket should contain "Use microservices"

  Scenario: Create a ticket with acceptance criteria
    When I run "ticket create 'Story ticket' --acceptance 'Should pass all tests'"
    Then the command should succeed
    And the created ticket should contain "## Acceptance Criteria"
    And the created ticket should contain "Should pass all tests"

  Scenario: Ticket has default status open
    When I run "ticket create 'New ticket'"
    Then the command should succeed
    And the created ticket should have field "status" with value "open"

  Scenario: Ticket has default priority 2
    When I run "ticket create 'Normal priority'"
    Then the command should succeed
    And the created ticket should have field "priority" with value "2"

  Scenario: Ticket has default type task
    When I run "ticket create 'Default type'"
    Then the command should succeed
    And the created ticket should have field "type" with value "task"

  Scenario: Ticket has empty deps by default
    When I run "ticket create 'No deps'"
    Then the command should succeed
    And the created ticket should have field "deps" with value "[]"

  Scenario: Ticket has empty links by default
    When I run "ticket create 'No links'"
    Then the command should succeed
    And the created ticket should have field "links" with value "[]"

  Scenario: Ticket has created timestamp
    When I run "ticket create 'Timestamped'"
    Then the command should succeed
    And the created ticket should have a valid created timestamp

  Scenario: Tickets directory created on demand
    Given the tickets directory does not exist
    When I run "ticket create 'First ticket'"
    Then the command should succeed
    And the tickets directory should exist

Feature: Ticket Dependencies
  As a user
  I want to manage ticket dependencies
  So that I can track blocking relationships

  Background:
    Given a clean tickets directory
    And a ticket exists with ID "task-0001"
    And a ticket exists with ID "task-0002"
    And a ticket exists with ID "task-0003"

  Scenario: Add a dependency
    When I run "ticket dep task-0001 task-0002"
    Then the command should succeed
    And the output should be "Added dependency: task-0001 -> task-0002"
    And ticket "task-0001" should have "task-0002" in deps

  Scenario: Add dependency is idempotent
    Given ticket "task-0001" depends on "task-0002"
    When I run "ticket dep task-0001 task-0002"
    Then the command should succeed
    And the output should be "Dependency already exists"

  Scenario: Remove a dependency
    Given ticket "task-0001" depends on "task-0002"
    When I run "ticket undep task-0001 task-0002"
    Then the command should succeed
    And the output should be "Removed dependency: task-0001 -/-> task-0002"
    And ticket "task-0001" should not have "task-0002" in deps

  Scenario: Remove non-existent dependency
    When I run "ticket undep task-0001 task-0002"
    Then the command should fail
    And the output should be "Dependency not found"

  Scenario: Add dependency with non-existent ticket
    When I run "ticket dep task-0001 nonexistent"
    Then the command should fail
    And the output should contain "Error: ticket 'nonexistent' not found"

  Scenario: Add dependency to non-existent ticket
    When I run "ticket dep nonexistent task-0001"
    Then the command should fail
    And the output should contain "Error: ticket 'nonexistent' not found"

  Scenario: View dependency tree
    Given ticket "task-0001" depends on "task-0002"
    And ticket "task-0002" depends on "task-0003"
    When I run "ticket dep tree task-0001"
    Then the command should succeed
    And the output should contain "task-0001"
    And the output should contain "task-0002"
    And the output should contain "task-0003"

  Scenario: Dependency tree shows status and name
    Given ticket "task-0001" depends on "task-0002"
    When I run "ticket dep tree task-0001"
    Then the command should succeed
    And the output should contain "[open]"
    And the output should contain "Main task"
    And the output should contain "Dependency task"

  Scenario: Dependency tree with multiple children
    Given ticket "task-0001" depends on "task-0002"
    And ticket "task-0001" depends on "task-0003"
    When I run "ticket dep tree task-0001"
    Then the command should succeed
    And the output should contain "task-0002"
    And the output should contain "task-0003"


Feature: Ticket Directory Resolution
  As a user
  I want tk to find .tickets by walking parent directories
  So that I can run commands from any subdirectory of my project

  Background:
    Given a clean tickets directory

  Scenario: Find tickets in current directory
    Given a ticket exists with ID "test-0001"
    When I run "ticket ls"
    Then the command should succeed
    And the output should contain "test-0001"

  Scenario: Find tickets in parent directory
    Given a ticket exists with ID "test-0001"
    And I am in subdirectory "src/components"
    When I run "ticket ls"
    Then the command should succeed
    And the output should contain "test-0001"

  Scenario: Find tickets in grandparent directory
    Given a ticket exists with ID "test-0001"
    And I am in subdirectory "src/components/ui"
    When I run "ticket ls"
    Then the command should succeed
    And the output should contain "test-0001"

  Scenario: Create ticket initializes in current directory when no parent has tickets
    Given the tickets directory does not exist
    And I am in subdirectory "new-project"
    When I run "ticket create 'First ticket'"
    Then the command should succeed
    And the output should match a ticket ID pattern
    And tickets directory should exist in current subdirectory

  Scenario: Error when no tickets directory for read command
    Given the tickets directory does not exist
    When I run "ticket show nonexistent"
    Then the command should fail
    And the output should contain "no .tickets directory found"

  Scenario: Error when no tickets directory in any parent
    Given the tickets directory does not exist
    And I am in subdirectory "orphan/deep/path"
    When I run "ticket ready"
    Then the command should fail
    And the output should contain "no .tickets directory found"

  Scenario: TICKETS_DIR env var takes priority over parent walking
    Given a ticket exists with ID "parent-0001"
    And a separate tickets directory exists at "other-tickets" with ticket "other-0001" named "Other ticket"
    And I am in subdirectory "src"
    When I run "ticket ls" with TICKETS_DIR set to "other-tickets"
    Then the command should succeed
    And the output should contain "other-0001"
    And the output should not contain "parent-0001"

  Scenario: Show command works from subdirectory
    Given a ticket exists with ID "test-0001"
    And I am in subdirectory "src"
    When I run "ticket show test-0001"
    Then the command should succeed
    And the output should contain "id: test-0001"

  Scenario: Dep command works from subdirectory
    Given a ticket exists with ID "task-0001"
    And a ticket exists with ID "task-0002"
    And I am in subdirectory "lib"
    When I run "ticket dep task-0001 task-0002"
    Then the command should succeed
    And the output should contain "Added dependency"

  Scenario: Help command works without tickets directory
    Given the tickets directory does not exist
    When I run "ticket help"
    Then the command should succeed
    And the output should contain "minimal ticket system"

Feature: Ticket Edit
  As a user
  I want to edit tickets in my editor
  So that I can make complex changes easily

  Background:
    Given a clean tickets directory
    And a ticket exists with ID "edit-0001"

  Scenario: Edit in non-TTY mode shows file path
    When I run "ticket edit edit-0001" in non-TTY mode
    Then the command should succeed
    And the output should contain "Edit ticket file:"
    And the output should contain ".tickets/edit-0001.md"

  Scenario: Edit non-existent ticket
    When I run "ticket edit nonexistent"
    Then the command should fail
    And the output should contain "Error: ticket 'nonexistent' not found"

  Scenario: Edit with partial ID
    When I run "ticket edit 0001" in non-TTY mode
    Then the command should succeed
    And the output should contain "edit-0001.md"

Feature: Ticket Links
  As a user
  I want to create symmetric links between tickets
  So that I can track related tickets

  Background:
    Given a clean tickets directory
    And a ticket exists with ID "link-0001"
    And a ticket exists with ID "link-0002"
    And a ticket exists with ID "link-0003"

  Scenario: Link two tickets
    When I run "ticket link link-0001 link-0002"
    Then the command should succeed
    And the output should contain "Added 2 link(s) between 2 tickets"
    And ticket "link-0001" should have "link-0002" in links
    And ticket "link-0002" should have "link-0001" in links

  Scenario: Link three tickets
    When I run "ticket link link-0001 link-0002 link-0003"
    Then the command should succeed
    And the output should contain "Added 6 link(s) between 3 tickets"
    And ticket "link-0001" should have "link-0002" in links
    And ticket "link-0001" should have "link-0003" in links
    And ticket "link-0002" should have "link-0001" in links
    And ticket "link-0002" should have "link-0003" in links
    And ticket "link-0003" should have "link-0001" in links
    And ticket "link-0003" should have "link-0002" in links

  Scenario: Link is idempotent
    Given ticket "link-0001" is linked to "link-0002"
    When I run "ticket link link-0001 link-0002"
    Then the command should succeed
    And the output should be "All links already exist"

  Scenario: Unlink two tickets
    Given ticket "link-0001" is linked to "link-0002"
    When I run "ticket unlink link-0001 link-0002"
    Then the command should succeed
    And the output should be "Removed link: link-0001 <-> link-0002"
    And ticket "link-0001" should not have "link-0002" in links
    And ticket "link-0002" should not have "link-0001" in links

  Scenario: Unlink non-existent link
    When I run "ticket unlink link-0001 link-0002"
    Then the command should fail
    And the output should be "Link not found"

  Scenario: Link with non-existent ticket
    When I run "ticket link link-0001 nonexistent"
    Then the command should fail
    And the output should contain "Error: ticket 'nonexistent' not found"

  Scenario: Partial linking adds only new links
    Given ticket "link-0001" is linked to "link-0002"
    When I run "ticket link link-0001 link-0002 link-0003"
    Then the command should succeed
    And the output should contain "Added 4 link(s) between 3 tickets"

Feature: Ticket Listing
  As a user
  I want to list tickets in various ways
  So that I can see what work needs to be done

  Background:
    Given a clean tickets directory

  Scenario: List all tickets
    Given a ticket exists with ID "list-0001"
    And a ticket exists with ID "list-0002"
    When I run "ticket ls"
    Then the command should succeed
    And the output should contain "list-0001"
    And the output should contain "list-0002"

  Scenario: List with status filter
    Given a ticket exists with ID "list-0001"
    And a ticket exists with ID "list-0002"
    And ticket "list-0002" has status "closed"
    When I run "ticket ls --status=open"
    Then the command should succeed
    And the output should contain "list-0001"
    And the output should not contain "list-0002"

  Scenario: List shows dependencies
    Given a ticket exists with ID "list-0001"
    And a ticket exists with ID "list-0002"
    And ticket "list-0001" depends on "list-0002"
    When I run "ticket ls"
    Then the command should succeed
    And the output should contain "<- [list-0002]"

  Scenario: List with no tickets returns nothing
    When I run "ticket ls"
    Then the output should be empty

  Scenario: Ready shows tickets with no deps and with closed deps
    Given a ticket exists with ID "ready-001"
    And a ticket exists with ID "ready-002"
    And a ticket exists with ID "ready-003"
    And ticket "ready-002" depends on "ready-003"
    And ticket "ready-003" has status "closed"
    When I run "ticket ready"
    Then the command should succeed
    And the output should contain "ready-001"
    And the output should contain "ready-002"

  Scenario: Ready excludes tickets with unclosed deps
    Given a ticket exists with ID "ready-001"
    And a ticket exists with ID "ready-002"
    And ticket "ready-001" depends on "ready-002"
    When I run "ticket ready"
    Then the command should succeed
    And the output should not contain "ready-001"
    And the output should contain "ready-002"

  Scenario: Ready shows tickets when deps are closed
    Given a ticket exists with ID "ready-001"
    And a ticket exists with ID "ready-002"
    And ticket "ready-001" depends on "ready-002"
    And ticket "ready-002" has status "closed"
    When I run "ticket ready"
    Then the command should succeed
    And the output should contain "ready-001"

  Scenario: Ready excludes closed tickets
    Given a ticket exists with ID "ready-001"
    And ticket "ready-001" has status "closed"
    When I run "ticket ready"
    Then the command should succeed
    And the output should not contain "ready-001"

  Scenario: Blocked shows tickets with unclosed deps
    Given a ticket exists with ID "block-001"
    And a ticket exists with ID "block-002"
    And ticket "block-001" depends on "block-002"
    When I run "ticket blocked"
    Then the command should succeed
    And the output should contain "block-001"
    And the output should contain "<- [block-002]"

  Scenario: Blocked excludes tickets with all deps closed
    Given a ticket exists with ID "block-001"
    And a ticket exists with ID "block-002"
    And ticket "block-001" depends on "block-002"
    And ticket "block-002" has status "closed"
    When I run "ticket blocked"
    Then the command should succeed
    And the output should not contain "block-001"

  Scenario: Blocked excludes closed tickets
    Given a ticket exists with ID "block-001"
    And a ticket exists with ID "block-002"
    And ticket "block-001" depends on "block-002"
    And ticket "block-001" has status "closed"
    When I run "ticket blocked"
    Then the command should succeed
    And the output should not contain "block-001"

  Scenario: Blocked shows only unclosed blockers
    Given a ticket exists with ID "block-001"
    And a ticket exists with ID "block-002"
    And a ticket exists with ID "block-003"
    And ticket "block-001" depends on "block-002"
    And ticket "block-001" depends on "block-003"
    And ticket "block-003" has status "closed"
    When I run "ticket blocked"
    Then the command should succeed
    And the output should contain "<- [block-002]"
    And the output should not contain "block-003"

  Scenario: Closed excludes open tickets
    Given a ticket exists with ID "done-0001"
    When I run "ticket closed"
    Then the command should succeed
    And the output should not contain "done-0001"

Feature: Ticket Notes
  As a user
  I want to add notes to tickets
  So that I can track progress and updates

  Background:
    Given a clean tickets directory
    And a ticket exists with ID "note-0001"

  Scenario: Add a note to ticket
    When I run "ticket add-note note-0001 'This is my note'"
    Then the command should succeed
    And the output should be "Note added to note-0001"
    And ticket "note-0001" should contain "## Notes"
    And ticket "note-0001" should contain "This is my note"

  Scenario: Note has timestamp
    When I run "ticket add-note note-0001 'Timestamped note'"
    Then the command should succeed
    And ticket "note-0001" should contain a timestamp in notes

  Scenario: Add multiple notes
    When I run "ticket add-note note-0001 'First note'"
    And I run "ticket add-note note-0001 'Second note'"
    Then ticket "note-0001" should contain "First note"
    And ticket "note-0001" should contain "Second note"

  Scenario: Add note to ticket that already has notes section
    Given ticket "note-0001" has a notes section
    When I run "ticket add-note note-0001 'Additional note'"
    Then the command should succeed
    And ticket "note-0001" should contain "Additional note"

  Scenario: Add note with empty string adds timestamp-only note
    When I run "ticket add-note note-0001 ''"
    Then the command should succeed
    And the output should be "Note added to note-0001"
    And ticket "note-0001" should contain "## Notes"

  Scenario: Add note to non-existent ticket
    When I run "ticket add-note nonexistent 'My note'"
    Then the command should fail
    And the output should contain "Error: ticket 'nonexistent' not found"

  Scenario: Add note with partial ID
    When I run "ticket add-note 0001 'Partial ID note'"
    Then the command should succeed
    And the output should be "Note added to note-0001"

Feature: Ticket Query
  As a user
  I want to query tickets as JSON
  So that I can process ticket data programmatically

  Background:
    Given a clean tickets directory

  Scenario: Query all tickets as JSONL
    Given a ticket exists with ID "query-001"
    And a ticket exists with ID "query-002"
    When I run "ticket query"
    Then the command should succeed
    And the output should be valid JSONL
    And the output should contain "query-001"
    And the output should contain "query-002"

  Scenario: Query with jq filter
    Given a ticket exists with ID "query-001"
    And a ticket exists with ID "query-002"
    And ticket "query-002" has status "closed"
    When I run "ticket query '.status == \"open\"'"
    Then the command should succeed
    And the output should contain "query-001"
    And the output should not contain "query-002"

  Scenario: Query includes all fields
    Given a ticket exists with ID "query-001"
    When I run "ticket query"
    Then the command should succeed
    And the JSONL output should have field "id"
    And the JSONL output should have field "status"
    And the JSONL output should have field "deps"
    And the JSONL output should have field "links"
    And the JSONL output should have field "type"
    And the JSONL output should have field "priority"

  Scenario: Query with no tickets
    When I run "ticket query"
    Then the output should be empty

  Scenario: Query arrays are JSON arrays
    Given a ticket exists with ID "query-001"
    And a ticket exists with ID "query-002"
    And ticket "query-001" depends on "query-002"
    When I run "ticket query"
    Then the command should succeed
    And the JSONL deps field should be a JSON array

Feature: Ticket Show
  As a user
  I want to view ticket details
  So that I can see full information about a ticket

  Background:
    Given a clean tickets directory

  Scenario: Show displays ticket content
    Given a ticket exists with ID "show-001"
    When I run "ticket show show-001"
    Then the command should succeed
    And the output should contain "id: show-001"
    And the output should contain "# Test ticket"

  Scenario: Show displays all frontmatter fields
    Given a ticket exists with ID "show-001"
    When I run "ticket show show-001"
    Then the command should succeed
    And the output should contain "status: open"
    And the output should contain "deps: []"
    And the output should contain "links: []"
    And the output should contain "type: task"
    And the output should contain "priority: 2"

  Scenario: Show displays blockers section
    Given a ticket exists with ID "show-001"
    And a ticket exists with ID "show-002"
    And ticket "show-001" depends on "show-002"
    When I run "ticket show show-001"
    Then the command should succeed
    And the output should contain "## Blockers"
    And the output should contain "show-002 [open] Blocker ticket"

  Scenario: Show hides blockers section when all deps closed
    Given a ticket exists with ID "show-001"
    And a ticket exists with ID "show-002"
    And ticket "show-001" depends on "show-002"
    And ticket "show-002" has status "closed"
    When I run "ticket show show-001"
    Then the command should succeed
    And the output should not contain "## Blockers"

  Scenario: Show displays blocking section
    Given a ticket exists with ID "show-001"
    And a ticket exists with ID "show-002"
    And ticket "show-002" depends on "show-001"
    When I run "ticket show show-001"
    Then the command should succeed
    And the output should contain "## Blocking"
    And the output should contain "show-002 [open] Blocked"

  Scenario: Show displays children section
    Given a ticket exists with ID "show-001"
    And a ticket exists with ID "show-002" with parent "show-001"
    When I run "ticket show show-001"
    Then the command should succeed
    And the output should contain "## Children"
    And the output should contain "show-002 [open] Child"

  Scenario: Show displays linked section
    Given a ticket exists with ID "show-001"
    And a ticket exists with ID "show-002"
    And ticket "show-001" is linked to "show-002"
    When I run "ticket show show-001"
    Then the command should succeed
    And the output should contain "## Linked"
    And the output should contain "show-002 [open] Second"

  Scenario: Show enhances parent field with name
    Given a ticket exists with ID "show-001"
    And a ticket exists with ID "show-002" with parent "show-001"
    When I run "ticket show show-002"
    Then the command should succeed
    And the output should contain "parent: show-001"
    And the output should contain "# Parent ticket"

  Scenario: Show non-existent ticket
    When I run "ticket show nonexistent"
    Then the command should fail
    And the output should contain "Error: ticket 'nonexistent' not found"

  Scenario: Show with partial ID
    Given a ticket exists with ID "show-001"
    When I run "ticket show 001"
    Then the command should succeed
    And the output should contain "id: show-001"

Feature: Ticket Status Management
  As a user
  I want to change ticket statuses
  So that I can track progress on tasks

  Background:
    Given a clean tickets directory
    And a ticket exists with ID "test-0001"

  Scenario: Set status to in_progress
    When I run "ticket status test-0001 in_progress"
    Then the command should succeed
    And the output should be "Updated test-0001 -> in_progress"
    And ticket "test-0001" should have field "status" with value "in_progress"

  Scenario: Set status to closed
    When I run "ticket status test-0001 closed"
    Then the command should succeed
    And the output should be "Updated test-0001 -> closed"
    And ticket "test-0001" should have field "status" with value "closed"

  Scenario: Set status to open
    Given ticket "test-0001" has status "closed"
    When I run "ticket status test-0001 open"
    Then the command should succeed
    And the output should be "Updated test-0001 -> open"
    And ticket "test-0001" should have field "status" with value "open"

  Scenario: Start command sets status to in_progress
    When I run "ticket start test-0001"
    Then the command should succeed
    And the output should be "Updated test-0001 -> in_progress"
    And ticket "test-0001" should have field "status" with value "in_progress"

  Scenario: Close command sets status to closed
    When I run "ticket close test-0001"
    Then the command should succeed
    And the output should be "Updated test-0001 -> closed"
    And ticket "test-0001" should have field "status" with value "closed"

  Scenario: Reopen command sets status to open
    Given ticket "test-0001" has status "closed"
    When I run "ticket reopen test-0001"
    Then the command should succeed
    And the output should be "Updated test-0001 -> open"
    And ticket "test-0001" should have field "status" with value "open"

  Scenario: Invalid status value
    When I run "ticket status test-0001 invalid"
    Then the command should fail
    And the output should contain "Error: invalid status 'invalid'"
    And the output should contain "open in_progress closed"

  Scenario: Status of non-existent ticket
    When I run "ticket status nonexistent open"
    Then the command should fail
    And the output should contain "Error: ticket 'nonexistent' not found"

  Scenario: Status command with partial ID
    When I run "ticket status 0001 in_progress"
    Then the command should succeed
    And ticket "test-0001" should have field "status" with value "in_progress"

Feature: Ticket Safety
  As a user
  I want safe and predictable ticket behavior
  So that my environment and workflows are protected over time

  Background:
    Given a clean tickets directory

  Scenario: Reject path traversal patterns in ticket id
    Given a ticket exists with ID "safe-0001"
    When I run "ticket show ../safe-0001"
    Then the command should fail
    And the output should contain "Error: invalid ticket id"

  Scenario: Reject absolute paths in ticket id
    Given a ticket exists with ID "safe-0002"
    When I run "ticket show C:\\Windows\\System32\\drivers\\etc\\hosts"
    Then the command should fail
    And the output should contain "Error: invalid ticket id"

  Scenario: Reject suspicious ids in link command
    Given a ticket exists with ID "sec-1000"
    When I run "ticket link sec-1000 ../../etc/passwd"
    Then the command should fail
    And the output should contain "Error: invalid ticket id"

  Scenario: Help output must not leak environment values
    Given the environment variable "API_KEY" is set to "super-secret"
    When I run "ticket help"
    Then the command should succeed
    And the output should not contain "super-secret"

  Scenario: List completes quickly with many tickets
    Given 1000 tickets exist
    When I run "ticket list"
    Then the command should succeed
    And the command should complete within "2s"

  Scenario: Query completes quickly for JSON output
    Given 1000 tickets exist
    When I run "ticket query"
    Then the command should succeed
    And the command should complete within "3s"

  Scenario: Dependency tree completes quickly for deep chains
    Given a chain of 200 dependent tickets exists
    When I run "ticket dep tree"
    Then the command should succeed
    And the command should complete within "3s"

  Scenario: Show completes quickly for a single ticket
    Given a ticket exists with ID "perf-0001"
    When I run "ticket show perf-0001"
    Then the command should succeed
    And the command should complete within "500ms"

  Scenario: Exact id takes precedence over partial match
    Given a ticket exists with ID "abc"
    And a ticket exists with ID "abc-1234"
    When I run "ticket show abc"
    Then the command should succeed
    And the output should contain "id: abc"

  Scenario: Adding an existing dependency stays idempotent
    Given a ticket exists with ID "cmp-0001"
    And a ticket exists with ID "cmp-0002"
    And ticket "cmp-0001" depends on "cmp-0002"
    When I run "ticket dep cmp-0001 cmp-0002"
    Then the command should succeed
    And the output should be "Dependency already exists"

  Scenario: Unlinking a non-existent link leaves links empty
    Given a ticket exists with ID "cmp-0003"
    And a ticket exists with ID "cmp-0004"
    When I run "ticket unlink cmp-0003 cmp-0004"
    Then the command should fail
    And the output should be "Link not found"
    And ticket "cmp-0003" should have field "links" with value "[]"
    And ticket "cmp-0004" should have field "links" with value "[]"

  Scenario: Listing with no tickets stays empty
    Given no tickets exist
    When I run "ticket list"
    Then the command should succeed
    And the output should be empty

  Scenario: Resolve exact id in isolation
    Given existing ticket IDs are "abc-1234", "abc-5678", "xyz-9999"
    When I resolve ticket id "abc-1234"
    Then the resolved ticket id should be "abc-1234"

  Scenario: Resolve suffix in isolation
    Given existing ticket IDs are "abc-1234", "abc-5678", "xyz-9999"
    When I resolve ticket id "1234"
    Then the resolved ticket id should be "abc-1234"

  Scenario: Resolve ambiguous prefix in isolation
    Given existing ticket IDs are "abc-1234", "abc-5678", "xyz-9999"
    When I resolve ticket id "abc"
    Then the resolution should fail
    And the error should contain "ambiguous"

  Scenario: Resolve unknown id in isolation
    Given existing ticket IDs are "abc-1234", "abc-5678", "xyz-9999"
    When I resolve ticket id "nope"
    Then the resolution should fail
    And the error should contain "not found"

Feature: Ticket User Journeys
  As a user
  I want the CLI to behave predictably in real usage
  So that I can manage work without surprises

  Background:
    Given a clean tickets directory

  Scenario: Create then show works in a normal flow
    When I run "ticket create 'Flow ticket'"
    Then the command should succeed
    And the output should match a ticket ID pattern
    When I run "ticket show last"
    Then the command should succeed
    And the output should contain "Flow ticket"

  Scenario: Help works without tickets directory
    Given the tickets directory does not exist
    When I run "ticket help"
    Then the command should succeed
    And the output should contain "Usage:"

  Scenario: Using TICKETS_DIR works in a normal flow
    Given the environment variable "TICKETS_DIR" is set to "./tmp_tickets"
    When I run "ticket create 'Env dir ticket'"
    Then the command should succeed
    And the tickets directory should exist

  Scenario: Create then close then list shows closed ticket
    When I run "ticket create 'Close flow ticket'"
    Then the command should succeed
    And the output should match a ticket ID pattern
    When I run "ticket close last"
    Then the command should succeed
    When I run "ticket list --status closed"
    Then the command should succeed
