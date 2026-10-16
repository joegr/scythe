Feature: Answering and linking cards
  Cards argue with each other. A link is {"rel", "to"} in the front matter of the card it starts
  from; the Action renders it as a line such as "Answers #12" in the card's issue, which GitHub
  records as a cross-reference on #12, so the answered card can list its answers (frontlines).
  Relations: answers, supports, contradicts, elaborates, same_claim, quotes, cites, derived_from,
  related.

  Background:
    Given I am signed in to the team's evidence
    And a card "Nuclear winter is real <run>" with the text "Soot from burning cities would block sunlight for a decade."
    And another card "Winter models overstate soot <run>" with the text "Newer fire models find far less soot reaches the stratosphere."

  @built @slow @signed-in
  Scenario: Mark one card as answering another
    When I open the other card
    And I link it with "Answers" to "Nuclear winter is real <run>"
    Then the other card's front matter links "answers" to the first card
    And the latest commit to the other card reads "answers #<first> (#<other>)"
    And the other card shows "Answers"

  @built @slow
  Scenario: The answered card lists its answers
    Given the other card links "answers" to the first card
    Then within 5 minutes the first card's page lists "Winter models overstate soot <run>"

  @built @signed-in
  Scenario: Unlink
    Given the other card links "supports" to the first card
    When I open the other card
    And I unlink "supports" to the first card
    Then the other card's front matter has no links
    And the latest commit to the other card reads "unlink supports #<first> (#<other>)"

  @partly
  # today: "Winter models overstate soot same claim as this card"
  Scenario Outline: Links read as sentences from the other side
    Given the other card links "<rel>" to the first card
    When I open the first card
    Then I see "<reads>"

    Examples:
      | rel         | reads                                                  |
      | answers     | Winter models overstate soot answers this card         |
      | same_claim  | Winter models overstate soot makes the same claim      |
      | contradicts | Winter models overstate soot contradicts this card     |

  @missing @signed-in
  Scenario: Frontlines: every answer to a card, ready to print
    Given three cards answer the first card
    When I print the first card's frontlines
    Then the print shows the first card followed by its three answers
