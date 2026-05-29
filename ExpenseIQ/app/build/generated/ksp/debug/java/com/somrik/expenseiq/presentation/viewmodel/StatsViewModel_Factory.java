package com.somrik.expenseiq.presentation.viewmodel;

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
public final class StatsViewModel_Factory implements Factory<StatsViewModel> {
  private final Provider<ExpenseRepository> repoProvider;

  public StatsViewModel_Factory(Provider<ExpenseRepository> repoProvider) {
    this.repoProvider = repoProvider;
  }

  @Override
  public StatsViewModel get() {
    return newInstance(repoProvider.get());
  }

  public static StatsViewModel_Factory create(Provider<ExpenseRepository> repoProvider) {
    return new StatsViewModel_Factory(repoProvider);
  }

  public static StatsViewModel newInstance(ExpenseRepository repo) {
    return new StatsViewModel(repo);
  }
}
