Feature: Reading a card three ways
  The full card shows every word; the read-aloud view keeps only marked runs (Scythe MD
  condensed rendering, unread stretches become " … "); the plain text view is the canonical
  Scythe MD: <u>underline</u>, ==highlight==, **emphasis**, nested in that fixed order. On
  screen the marks are drawn as thin, heavy and double underlines.

  Background:
    Given a card "Soot <run>" with the text:
      """
      Nuclear war would cause human extinction. Soot from burning cities would block sunlight for a decade.
      """
    And the card has a "highlight" span over "block sunlight"
    And the card has a "emphasis" span over "decade"

  @built
  Scenario: The full card shows every word
    When I open the card
    Then the card shows "Nuclear war would cause human extinction."

  @built
  Scenario: Read-aloud keeps only what you'd say in the speech
    When I open the card
    And I switch to the read-aloud view
    Then the card shows "block sunlight"
    And the card does not show "Nuclear war would cause human extinction."

  @built
  Scenario: Plain text is the card as text you can paste anywhere
    When I open the card
    And I switch to the plain text view
    Then the plain text reads "Nuclear war would cause human extinction. Soot from burning cities would ==block sunlight== for a **decade**."

  @partly
  # today: read-aloud drops unmarked text, so a new card looks empty in Home, Search and Library
  Scenario: A card with nothing marked yet still shows its words in lists
    Given a card "Fresh <run>" with the text "Nothing is marked in this card yet."
    When I look at the latest cards
    Then the card "Fresh <run>" shows "Nothing is marked in this card yet."

  @missing
  # decision needed: the design rule is underline-only, but debaters read highlight as color
  Scenario: Highlight looks like highlight
    When I open the card
    Then "block sunlight" is drawn with a highlight color, not only a heavier underline
