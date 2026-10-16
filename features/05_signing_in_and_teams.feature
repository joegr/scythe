Feature: Signing in and choosing the team's evidence
  Anyone can read a team's evidence: the repo is public and reads go straight to the GitHub API.
  Saving needs a fine-grained GitHub token with Contents and Issues write on that repo, made from a
  pre-filled link and kept only in this browser. A debater can choose which team's evidence (repo)
  they work in; where Scythe saves (GitHub API base, passthrough, local API) is fixed by the build
  and can never be changed from the browser.

  @built
  Scenario: Read the team's evidence without signing in
    Given I am not signed in
    And a card "Open evidence <run>" with the text "Reading needs no account."
    When I open the card
    Then the card shows "Reading needs no account."
    And I see "Sign in to edit."

  @built
  Scenario: The sign-in link asks GitHub for exactly what Scythe needs
    Given I am not signed in
    When I open Scythe
    And I start signing in
    Then the sign-in link opens GitHub's new fine-grained token page
    And the link asks for "contents" "write" and "issues" "write"
    And the link sets the key to expire in "30" days and belong to "joegr"

  @built
  Scenario: A debater can choose the team, and nothing else
    Given I am signed in to the team's evidence
    When I open Scythe
    And I open the team settings
    Then the settings have exactly one field, for the team's evidence
    And the settings have no field for where Scythe saves

  @built @signed-in
  Scenario: Old saved backend addresses in the browser are ignored
    Given I am signed in to the team's evidence
    And this browser still has old saved addresses for the GitHub API and the passthrough
    And a card "Pinned backend <run>" with the text "Saves go where the build says."
    When I open the card
    And I select "Saves" in the card
    And I press "1"
    Then the card in git gains a "underline" span over "Saves"

  @partly
  # today: any working GitHub key signs in; the first save then fails with "Check that the token has Issues: write"
  Scenario: A key that can't save to this team's evidence is caught at sign-in
    Given I have a GitHub key that can read but not write the team's evidence
    When I sign in with it
    Then I see "This key can read your team's evidence but can't save to it. Make a new key and pick your team's evidence when GitHub asks where it can be used."
    And I am not signed in

  @partly
  # today: works through settings, but the screen says "Repository (public; cards are its issues)" and "owner/repo"
  Scenario: Switch between two teams' evidence
    Given I am signed in to the team's evidence
    When I switch to the evidence "joegr/scythe"
    Then the latest cards are from "joegr/scythe"
    And my GitHub key is kept

  @missing
  # today: clicking your name signs you out at once
  Scenario: Signing out asks first
    Given I am signed in to the team's evidence
    When I click my name
    Then I see "Sign out of Scythe on this browser?"
    And I am still signed in until I confirm
