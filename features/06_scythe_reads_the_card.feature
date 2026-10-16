Feature: Scythe reads the card's words
  On every push touching cards/**, the scythe.yml Action runs spaCy (en_core_web_sm) over the card,
  re-snaps every span with doc.char_span(start, end, alignment_mode="expand"), drops spans that
  cover no token, and writes the result into the card's issue: rendered card, token offsets
  (start/end), entities, and processed = {model, text_sha, tokens, file_sha}. The card is "checked"
  when processed.file_sha equals the blob sha of the cards/<n>.md the page loaded.

  Background:
    Given I am signed in to the team's evidence
    And a card "Checked <run>" with the text:
      """
      Alan Robock of Rutgers University found that soot from burning cities would block sunlight.
      """

  @built @slow @signed-in
  Scenario: After a save, Scythe checks that exact version
    When I open the card
    And I select "soot from burning" in the card
    And I press "1"
    Then within 5 minutes the card's issue records processed.file_sha equal to the card's blob sha
    And the issue's "underline" span over "soot from burning" has token offsets with start before end

  @built @slow
  Scenario: The issue shows the card the way GitHub can draw it
    Given the card has a "underline" span over "soot from burning cities"
    And the card has a "highlight" span over "block sunlight"
    Then within 5 minutes the card's issue body contains "<ins>soot from burning cities</ins>"
    And the card's issue body contains "<mark>block sunlight</mark>"
    And the card's issue has the labels "scythe:card" and "topic:cx-2025-26-exploration-development-arctic"

  @partly @slow @signed-in
  # today: "spaCy is processing this version" / "spaCy is up to date with this version"
  Scenario: The card says when its words have been checked
    When I open the card
    And I select "block sunlight" in the card
    And I press "2"
    Then I see "Checking words…"
    And within 5 minutes I see "Words checked"

  @partly @slow @signed-in
  # today: the page stops looking after 20 tries (2 minutes) and says "processing" until reload
  Scenario: Checking never gets stuck on screen
    Given the Action takes 4 minutes to check the card
    When I keep the card open
    Then I see "Words checked" without reloading

  @partly @slow
  # today: snapped offsets live only in the issue; cards/<n>.md keeps the browser's offsets
  Scenario: When Scythe's word boundaries differ, the card in git follows Scythe
    Given the card has a "underline" span whose browser snapping differs from spaCy's tokens
    When Scythe has checked the card
    Then cards/<n>.md holds the spaCy-snapped character offsets
