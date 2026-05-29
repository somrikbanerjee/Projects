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
public final class AccountViewModel_Factory implements Factory<AccountViewModel> {
  private final Provider<ExpenseRepository> repoProvider;

  public AccountViewModel_Factory(Provider<ExpenseRepository> repoProvider) {
    this.repoProvider = repoProvider;
  }

  @Override
  public AccountViewModel get() {
    return newInstance(repoProvider.get());
  }

  public static AccountViewModel_Factory create(Provider<ExpenseRepository> repoProvider) {
    return new AccountViewModel_Factory(repoProvider);
  }

  public static AccountViewModel newInstance(ExpenseRepository repo) {
    return new AccountViewModel(repo);
  }
}
