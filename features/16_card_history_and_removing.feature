Feature: A card's history, and removing a card
  Every change to a card is a commit of cards/<n>.md, so `git log -- cards/<n>.md` is the card's
  history: who changed what, and when. Removing (archiving) a card deletes the file with a
  commit; the Action then closes the issue as not planned. Every version stays in git.

  Background:
    Given I am signed in to the team's evidence
    And a card "History <run>" with the text "Soot from burning cities would block sunlight for a decade."

  @built @signed-in
  Scenario: The history lists every change, newest first
    Given the card has a "underline" span over "Soot from burning cities"
    And the card has a "highlight" span over "block sunlight"
    When I open the card
    And I open the card's history
    Then the history lists, newest first:
      | highlight: "block sunlight" (#<n>)           |
      | underline: "Soot from burning cities" (#<n>) |
      | card: History <run> (#<n>)                    |
    And each history entry names who made it

  @partly @signed-in
  # today: each entry shows a 7-character commit id and the raw commit message
  Scenario: History reads as sentences
    Given the card has a "highlight" span over "block sunlight"
    When I open the card
    And I open the card's history
    Then I see "You highlighted “block sunlight”"

  @missing @signed-in
  Scenario: Open an earlier version
    Given the card has a "highlight" span over "block sunlight"
    When I open the version before the highlight
    Then the card shows no highlight
    And I can put that version back, which saves it as a new change

  @partly @signed-in
  # today: archive acts at once, with no question, and a failure does nothing visible
  Scenario: Removing a card asks first, and says if it failed
    When I open the card
    And I remove the card
    Then I see "Remove this card? It stays in the history and can be brought back."
    When I confirm
    Then cards/<n>.md is deleted with the commit "archive: History <run> (#<n>)"

  @missing @signed-in
  Scenario: Bring a removed card back
    Given the card was removed
    When I search the removed cards and open it
    And I bring it back
    Then cards/<n>.md is restored from its last version and its issue reopens
