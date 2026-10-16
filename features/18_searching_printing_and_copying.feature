Feature: Searching, printing and copying
  Search uses GitHub issue search over the card issues (title = tag, body = cite, rendered card
  and hidden meta), filtered by labels such as "topic:<slug>" and "approved". Print renders
  canonical Scythe MD for one card or a whole file. Copy puts Word-ready HTML on the clipboard in
  Verbatim style: underline, cyan (#00ffff) highlight, bold boxed emphasis, 8pt unread text.

  Background:
    Given a card "Searchable soot <run>" with the text "Soot from burning cities would block sunlight for a decade."
    And the card has a "highlight" span over "block sunlight"

  @built @slow
  Scenario: Find a card by the words in its tag
    When I search the team's evidence for "Searchable soot <run>"
    Then within 3 minutes the results include "Searchable soot <run>"

  @partly
  # today: "1 cards"
  Scenario: The count reads like English
    When I search the team's evidence for "Searchable soot <run>"
    Then I see "1 card"

  @partly
  # today: the search box isn't in the address, so a search can't be sent to a partner
  Scenario: Share a search as a link
    When I search the team's evidence for "Searchable soot <run>"
    Then the address includes the search
    And opening that address shows the same results

  @built
  Scenario: Print a card
    When I open the card's print page
    Then the print shows the tag "Searchable soot <run>"
    And the print shows "block sunlight" highlighted

  @built @signed-in
  Scenario: Copy into Word with Verbatim formatting
    Given I am signed in to the team's evidence
    When I open the card
    And I copy the card
    Then the clipboard's HTML draws "block sunlight" with background "#00ffff"
    And the clipboard's HTML draws unmarked words at "8pt"

  @partly
  # today: print draws highlight as a heavy underline, and the "read only" toggle means "only marked text"
  Scenario: Print a file as a speech document
    Given cards filed under file "Aff" in blocks "Inherency" and "Solvency"
    When I print the file "Aff"
    Then the print has the file name, then each block, then each card with its tag, cite and marked text
    And highlighted words print with a highlight color
