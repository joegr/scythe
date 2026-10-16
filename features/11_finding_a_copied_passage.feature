Feature: Finding a copied passage in a source
  Debaters often have the passage already, copied from a PDF or another card. locate() finds it
  in the source text: an exact match first, then a match that ignores runs of whitespace and treats
  straight and curly quotes, and hyphens and dashes, as the same. The match becomes the selection,
  so the cut is still the source's exact words.

  Background:
    Given I am signed in to the team's evidence
    And a pasted source "Quotes study <run>" by "Alan Robock" in "Nature Food" on "2022-08-15" with text:
      """
      Robock called it “the worst thing that could happen” — a decade-long winter.
      """

  @built @signed-in
  Scenario: Straight quotes, a hyphen and extra spaces still find the passage
    When I open that source in the reader
    And I find the copied passage "\"the worst   thing that could happen\" - a decade-long"
    Then the selection is 51 characters
    When I write the tag "Worst case <run>"
    And I cut the card
    Then I am on the new card
    And the card's text in git is exactly "“the worst thing that could happen” — a decade-long"

  @built @signed-in
  Scenario: A passage that isn't in the source says so
    When I open that source in the reader
    And I find the copied passage "a passage from some other article"
    Then I see "That passage isn’t in this source."

  @partly @signed-in
  # today: the message appears at the top of the reader, scrolled out of sight of the cut bar
  Scenario: The message shows next to where you pasted
    Given that source is a full-length article
    When I open that source in the reader
    And I find the copied passage "a passage from some other article"
    Then the message is visible without scrolling

  @missing @signed-in
  Scenario: A passage that appears twice asks which one
    Given the source contains "a decade-long winter" twice
    When I find the copied passage "a decade-long winter"
    Then I see "Found 2 times" and can step between them
