package com.somrik.expenseiq.presentation.viewmodel;

import com.somrik.expenseiq.data.pref.SettingsManager;
import com.somrik.expenseiq.data.repository.ExpenseRepository;
import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;

@ScopeMetadata
@QualifierMetadata
@DaggerGenerated
@Generated(
    value = "dagger.internal.codegen.ComponentProcessor",
    comments = "https://dagger.dev"
)
@SuppressWarnings({
    "unchecked",
    "rawtypes",
    "KotlinInternal",
    "KotlinInternalInJava",
    "cast"
})
public final class SettingsViewModel_Factory implements Factory<SettingsViewModel> {
  private final Provider<ExpenseRepository> repoProvider;

  private final Provider<SettingsManager> settingsManagerProvider;

  public SettingsViewModel_Factory(Provider<ExpenseRepository> repoProvider,
      Provider<SettingsManager> settingsManagerProvider) {
    this.repoProvider = repoProvider;
    this.settingsManagerProvider = settingsManagerProvider;
  }

  @Override
  public SettingsViewModel get() {
    return newInstance(repoProvider.get(), settingsManagerProvider.get());
  }

  public static SettingsViewModel_Factory create(Provider<ExpenseRepository> repoProvider,
      Provider<SettingsManager> settingsManagerProvider) {
    return new SettingsViewModel_Factory(repoProvider, settingsManagerProvider);
  }

  public static SettingsViewModel newInstance(ExpenseRepository repo,
      SettingsManager settingsManager) {
    return new SettingsViewModel(repo, settingsManager);
  }
}
