Feature: Marking up words in a card
  Underline, highlight and emphasis are spans with key "sc" and labels underline / highlight /
  emphasis. A span always covers whole words: the browser snaps a selection outward to the rough
  word tokens of roughTokens(), and the Action later re-snaps to spaCy tokens with
  char_span(alignment_mode="expand"). Each mark is a commit of cards/<n>.md pinned to the blob sha
  the card was loaded at.

  Background:
    Given I am signed in to the team's evidence
    And a card "Soot <run>" with the text:
      """
      Soot from burning cities would block sunlight for a decade.
      """

  @built @signed-in
  Scenario Outline: A key marks the selection, grown to whole words
    When I open the card
    And I select "<selection>" in the card
    And I press "<key>"
    Then the card in git gains a "<label>" span over "<words>"
    And the latest commit to the card reads "<label>: \"<words>\" (#<n>)"

    Examples:
      | selection     | key | label     | words             |
      | oot from burn | 1   | underline | Soot from burning |
      | block sunl    | 2   | highlight | block sunlight    |
      | decade        | 3   | emphasis  | decade            |

  @built @signed-in
  Scenario: Backspace removes the mark you clicked
    Given the card has a "underline" span over "Soot from burning"
    When I open the card
    And I click the marked words "Soot from burning"
    And I press "Backspace"
    Then the card in git has no "underline" span over "Soot from burning"
    And the latest commit to the card reads "remove underline: \"Soot from burning\" (#<n>)"

  @built @signed-in
  Scenario: Marks nest: highlight inside underline inside the same sentence
    Given the card has a "underline" span over "Soot from burning cities would block sunlight"
    And the card has a "highlight" span over "block sunlight"
    When I open the card
    And I switch to the plain text view
    Then the plain text reads "<u>Soot from burning cities would ==block sunlight==</u> for a decade."

  @missing @signed-in
  Scenario: Pressing the same key again takes the mark off
    Given the card has a "highlight" span over "block sunlight"
    When I open the card
    And I select "block sunlight" in the card
    And I press "2"
    Then the card in git has no "highlight" span over "block sunlight"

  @partly @signed-in
  # today: nothing happens and nothing is said; the "no words" message only shows for a non-empty selection
  Scenario: A selection with no words in it is refused out loud
    When I open the card
    And I select only the space after "Soot" in the card
    And I press "1"
    Then I see "That selection has no words in it."
    And no commit is made to the card

  @partly @signed-in
  # today: the Labels page asks for a "spans key" and draws custom marks as a 2px underline nobody can tell apart
  Scenario: A team adds its own mark for its own drills
    When the team adds a mark "warrant" on key "4"
    And I select "block sunlight" in the card and press "4"
    Then the card in git gains a "warrant" span over "block sunlight"
    And I see the mark "warrant" named when I point at those words
