Feature: The source shelf
  Every source is sources/<n>.md plus a "scythe:source" issue; every card cut from it records
  "source": n in its front matter and, once checked, is a sub-issue of the source's issue. A
  debater should be able to browse sources, see what was cut from each, and go back for more.

  Background:
    Given I am signed in to the team's evidence
    And a pasted source "Shelf study <run>" by "Alan Robock" in "Nature Food" on "2022-08-15" with text:
      """
      Soot from burning cities would block sunlight for a decade.
      """
    And a card "Shelf card <run>" cut from that source

  @built @signed-in
  Scenario: Go back to a card's source to cut more
    When I open the card
    And I open the card's source
    Then the reader shows the source "Shelf study <run>"
    And the reader shows "Soot from burning cities would block sunlight for a decade."

  @built @signed-in
  Scenario: Recent sources are a click away when cutting
    When I open the reader
    Then the recent sources include "Shelf study <run>"

  @built @slow
  Scenario: Cards hang under their source on GitHub
    Then within 5 minutes the card's issue is a sub-issue of the source's issue

  @missing
  Scenario: Browse every source and what was cut from it
    When I open the library
    Then I see a "Sources" section listing "Shelf study <run>"
    And under it the card "Shelf card <run>"

  @partly
  # today: deleting sources/<n>.md leaves its issue open; there is no way to remove a source in the app
  Scenario: Remove a source nobody cut from
    Given a source with no cards
    When I remove the source
    Then its file is deleted and its issue is closed
