Feature: Cutting a card from a source
  A card is a verbatim excerpt of a source: the debater selects the passage, writes the tag and
  checks the cite. Scythe never rewrites the words. The cut opens issue #n through the passthrough
  and commits cards/<n>.md, whose JSON front matter holds the tag (title), cite, source number,
  topic and the exact text.

  Background:
    Given I am signed in to the team's evidence
    And my resolution is "cx-2025-26-exploration-development-arctic"
    And a pasted source "Nuclear winter study <run>" by "Alan Robock" in "Nature Food" on "2022-08-15" with text:
      """
      Nuclear war would cause human extinction. Scientists at Rutgers University found that soot from burning cities would block sunlight for a decade.

      The resulting nuclear winter would collapse global agriculture, starving billions of people within two years.
      """

  @built @signed-in
  Scenario: Cut a passage exactly as written
    When I open that source in the reader
    And I select "soot from burning cities would block sunlight for a decade" in the source
    And I write the tag "Nuclear war causes extinction <run>"
    And I cut the card
    Then I am on the new card
    And the card's text in git is exactly "soot from burning cities would block sunlight for a decade"
    And the card's front matter has "title" "Nuclear war causes extinction <run>"
    And the card's front matter has "source" set to that source
    And the card's front matter has the topic slug "cx-2025-26-exploration-development-arctic"
    And the first commit to the card reads "card: Nuclear war causes extinction <run> (#<n>)"

  @built @signed-in
  Scenario: Whitespace around a selection is trimmed, nothing else changes
    When I open that source in the reader
    And I select " soot from burning cities " in the source
    And I write the tag "Soot <run>"
    And I cut the card
    Then I am on the new card
    And the card's text in git is exactly "soot from burning cities"

  @built @signed-in
  Scenario: A card needs a tag before it can be cut
    When I open that source in the reader
    And I select "The resulting nuclear winter" in the source
    Then the cut button is disabled
    When I write the tag "Winter <run>"
    Then the cut button is enabled

  @missing @signed-in
  Scenario: The cite, file and block stay filled in for the next cut
    Given I cut "Nuclear war would cause human extinction." from that source into file "Aff" block "Extinction"
    When I return to that source
    Then the cite still reads the source's cite
    And the file still reads "Aff" and the block "Extinction"
    And the tag is empty

  @missing @signed-in
  Scenario: Cut with the keyboard alone
    When I open that source in the reader
    And I move the cursor to "starving billions" and extend the selection with Shift and the arrow keys
    And I write the tag "Famine <run>"
    And I press Cmd+Enter
    Then I am on the new card
    And the card's text in git is exactly "starving billions"

  @partly @signed-in
  # today: the clip form on Home has no cite field and no busy state; a double click makes two cards
  Scenario: Quick card from a clip, with a cite and no duplicates
    When I paste a clip "Soot blocks the sun." tagged "Soot <run>" with cite "Robock 22"
    And I press "Create card" twice quickly
    Then exactly one card is created
    And the card's front matter has "cite" "Robock 22"
