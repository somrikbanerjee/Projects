package com.somrik.expenseiq.presentation.viewmodel;

import com.somrik.expenseiq.data.pref.SettingsManager;
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
public final class MainViewModel_Factory implements Factory<MainViewModel> {
  private final Provider<SettingsManager> settingsManagerProvider;

  public MainViewModel_Factory(Provider<SettingsManager> settingsManagerProvider) {
    this.settingsManagerProvider = settingsManagerProvider;
  }

  @Override
  public MainViewModel get() {
    return newInstance(settingsManagerProvider.get());
  }

  public static MainViewModel_Factory create(Provider<SettingsManager> settingsManagerProvider) {
    return new MainViewModel_Factory(settingsManagerProvider);
  }

  public static MainViewModel newInstance(SettingsManager settingsManager) {
    return new MainViewModel(settingsManager);
  }
}
