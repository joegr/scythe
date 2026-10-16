Feature: Suggested highlighting
  Scythe can learn a team's cutting style: a spaCy spancat model trained on the team's accepted
  spans (manual and imported) proposes underline and highlight spans on new cards. Suggestions
  are spans with src "model", a score and accepted=false until a debater accepts them. Today this
  runs only on the local API (Postgres index, `make train`, POST /api/cards/{id}/suggest); the
  Pages app never shows it.

  Background:
    Given the team has approved at least 50 cut cards
    And a model has been trained on the team's accepted spans

  @partly @signed-in
  # today: local API only; the Data page says "Span categorizer", "Base pipeline", "F / P / R"
  Scenario: Train on the team's cutting
    When the coach starts training from the team page
    Then I see "Learning from 50 cards…"
    And I see how often the suggestions match the team's own highlighting

  @partly @signed-in
  # today: local API only; never shown in the Pages app
  Scenario: Suggestions appear on a new card, waiting for a yes
    Given a new card "Suggest <run>" with no marks
    When I ask for suggestions
    Then suggested highlights are drawn as dotted underlines
    And none of them is in the card in git until I accept it

  @missing @signed-in
  Scenario: Accept a suggestion with Enter
    Given the card shows a suggested "highlight" over "block sunlight"
    When I click the suggestion
    And I press "Enter"
    Then the card in git gains a "highlight" span over "block sunlight"
    And the latest commit to the card reads "highlight: \"block sunlight\" (#<n>)"

  @missing @signed-in
  Scenario: Reject a suggestion with x, and it stays rejected
    Given the card shows a suggested "underline" over "for a decade"
    When I click the suggestion
    And I press "x"
    And I ask for suggestions again
    Then "for a decade" is not suggested again

  @missing
  Scenario: Suggestions only learn from cards the team approved
    Given an unapproved card with a "highlight" over every word
    When the model is trained
    Then that card is not in the training data
